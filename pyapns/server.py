from __future__ import with_statement
import _json as json
import base64
import struct, time
import logging
import binascii
import datetime
from StringIO import StringIO as _StringIO
from OpenSSL import SSL, crypto
from twisted.internet import reactor, defer
from twisted.internet.protocol import (
  ReconnectingClientFactory, ClientFactory, Protocol, ServerFactory)
from twisted.internet.ssl import ClientContextFactory
from twisted.application import internet, service
from twisted.protocols.basic import LineReceiver
from twisted.python import log
from zope.interface import Interface, implements
from twisted.web import xmlrpc, resource


APNS_SERVER_SANDBOX_HOSTNAME = "gateway.sandbox.push.apple.com"
APNS_SERVER_HOSTNAME = "gateway.push.apple.com"
APNS_SERVER_PORT = 2195
FEEDBACK_SERVER_SANDBOX_HOSTNAME = "feedback.sandbox.push.apple.com"
FEEDBACK_SERVER_HOSTNAME = "feedback.push.apple.com"
FEEDBACK_SERVER_PORT = 2196
APNS_STATUS_CODES = {
    0: 'No errors encountered',
    1: 'Processing error',
    2: 'Missing device token',
    3: 'Missing topic',
    4: 'Missing payload',
    5: 'Invalid token size',
    6: 'Invalid topic size',
    7: 'Invalid payload size',
    8: 'Invalid token',
    255: 'None (unknown)'
}

app_ids = {} # {'app_id': APNSService()}



class NotificationString(str):
  def __new__(cls, S, on_failure, tokens, notifications, expirys=None, identifiers=None):
    T = str.__new__(cls, S)
    T.on_failure = on_failure
    T.tokens = tokens
    T.notifications = notifications
    T.expirys = expirys
    T.identifiers = identifiers 
    T.debug = False
    return T


class StringIO(_StringIO):
  """Add context management protocol to StringIO
      ie: http://bugs.python.org/issue1286
  """
  
  def __enter__(self):
    if self.closed:
      raise ValueError('I/O operation on closed file')
    return self
  
  def __exit__(self, exc, value, tb):
    self.close()


class IAPNSService(Interface):
    """ Interface for APNS """
    
    def write(self, notification):
        """ Write the notification to APNS """
    
    def read(self):
        """ Read from the feedback service """


class APNSClientContextFactory(ClientContextFactory):
  def __init__(self, ssl_cert_file):
    log.msg('APNSClientContextFactory ssl_cert_file=%s' % ssl_cert_file)
    self.ctx = SSL.Context(SSL.SSLv3_METHOD)
    if 'BEGIN CERTIFICATE' in ssl_cert_file:
      cer = crypto.load_certificate(crypto.FILETYPE_PEM, ssl_cert_file)
      pkey = crypto.load_privatekey(crypto.FILETYPE_PEM, ssl_cert_file)
      self.ctx.use_certificate(cer)
      self.ctx.use_privatekey(pkey)
    else:
      self.ctx.use_certificate_file(ssl_cert_file)
      self.ctx.use_privatekey_file(ssl_cert_file)
  
  def getContext(self):
    return self.ctx


class APNSProtocol(Protocol):
  def connectionMade(self):
    log.msg('APNSProtocol connectionMade')
    self.last_messages = []
    self.last_error = None
    if 'timeout' in self.__dict__ and self.timeout:
      self.timeout.cancel()
    self.timeout = reactor.callLater(.750, self._timeout_last_sents)
    self.factory.addClient(self)
  
  def _timeout_last_sents(self):
    self.last_messages = []
    self.timeout = reactor.callLater(.750, self._timeout_last_sents)
  
  def sendMessage(self, msg):
    self.last_messages.append(msg)
    log.msg('APNSProtocol sendMessage msg=%s' % binascii.hexlify(msg))
    self.transport.write(msg)
    if msg.debug:
      self.transport.doWrite()
      time.sleep(.750)

  def dataReceived(self, data):
    try:
      self.last_error = decode_error_packet(data)
      log.msg('APNSProtocol dataReceived err=%s' % str(self.last_error))
    except:
      pass
  
  def connectionLost(self, reason):
    log.msg('APNSProtocol connectionLost')
    if 'timeout' in self.__dict__ and self.timeout:
      self.timeout.cancel()
    if self.last_messages:
      C = getattr(self.last_messages[-1], 'on_failure', lambda s: s)
      try:
        C(self.last_messages, reason, self.last_error)
      except Exception, e:
        log.msg('APNSProtocol could not call on_failure of last message %s' % str(e))
    self.last_messages = None
    self.last_error = None
    self.factory.removeClient(self)


class APNSFeedbackHandler(LineReceiver):
  MAX_LENGTH = 1024*1024
  
  def connectionMade(self):
    log.msg('feedbackHandler connectionMade')

  def rawDataReceived(self, data):
    log.msg('feedbackHandler rawDataReceived %s' % binascii.hexlify(data))
    self.io.write(data)
  
  def lineReceived(self, data):
    log.msg('feedbackHandler lineReceived %s' % binascii.hexlify(data))
    self.io.write(data)

  def connectionLost(self, reason):
    log.msg('feedbackHandler connectionLost %s' % reason)
    self.deferred.callback(self.io.getvalue())
    self.io.close()


class APNSFeedbackClientFactory(ClientFactory):
  protocol = APNSFeedbackHandler
  
  def __init__(self):
    self.deferred = defer.Deferred()
  
  def buildProtocol(self, addr):
    p = self.protocol()
    p.factory = self
    p.deferred = self.deferred
    p.io = StringIO()
    p.setRawMode()
    return p
  
  def startedConnecting(self, connector):
    log.msg('APNSFeedbackClientFactory startedConnecting')
  
  def clientConnectionLost(self, connector, reason):
    log.msg('APNSFeedbackClientFactory clientConnectionLost reason=%s' % reason)
    ClientFactory.clientConnectionLost(self, connector, reason)
  
  def clientConnectionFailed(self, connector, reason):
    log.msg('APNSFeedbackClientFactory clientConnectionFailed reason=%s' % reason)
    ClientFactory.clientConnectionLost(self, connector, reason)


class APNSClientFactory(ReconnectingClientFactory):
  protocol = APNSProtocol
  
  def __init__(self):
    self.clientProtocol = None
    self.deferred = defer.Deferred()
    self.deferred.addErrback(log_errback('APNSClientFactory __init__'))
  
  def addClient(self, p):
    self.clientProtocol = p
    self.deferred.callback(p)
  
  def removeClient(self, p):
    self.clientProtocol = None
    self.deferred = defer.Deferred()
    self.deferred.addErrback(log_errback('APNSClientFactory removeClient'))
  
  def startedConnecting(self, connector):
    log.msg('APNSClientFactory startedConnecting')
  
  def buildProtocol(self, addr):
    self.resetDelay()
    p = self.protocol()
    p.factory = self
    return p
  
  def clientConnectionLost(self, connector, reason):
    log.msg('APNSClientFactory clientConnectionLost reason=%s' % reason)
    ReconnectingClientFactory.clientConnectionLost(self, connector, reason)
  
  def clientConnectionFailed(self, connector, reason):
    log.msg('APNSClientFactory clientConnectionFailed reason=%s' % reason)
    ReconnectingClientFactory.clientConnectionFailed(self, connector, reason)


class APNSService(service.Service):
  """ A Service that sends notifications and receives 
  feedback from the Apple Push Notification Service
  """
  
  implements(IAPNSService)
  clientProtocolFactory = APNSClientFactory
  feedbackProtocolFactory = APNSFeedbackClientFactory
  
  def __init__(self, cert_path, environment, timeout=15, log_disconnections=False, debug=False):
    log.msg('APNSService __init__')
    self.factory = None
    self.environment = environment
    self.cert_path = cert_path
    self.raw_mode = False
    self.debug = debug
    self.timeout = timeout
    self.log_disconnections = log_disconnections
    self.log = []
  
  def getContextFactory(self):
    return APNSClientContextFactory(self.cert_path)

  def _log_disconnection(self, notes, reason, error):
    log.msg('APNSService _log_disconnection')
    info = {
        'last-messages': [],
        'error': error
    }
    for note in notes:
      info['last-messages'].append({
          'notifications': note.notifications,
          'tokens':        note.tokens,
          'reason':        str(reason),
          'identifiers':   note.identifiers,
          'expiriations':  note.expirys
      })
    self.log.append(['ssl-connection-lost', datetime.datetime.now(), info])

  def failure_callback(self):
    if self.log_disconnections:
      return self._log_disconnection
  
  def write(self, notifications):
    "Connect to the APNS service and send notifications"
    notifications.debug = self.debug
    if not self.factory:
      log.msg('APNSService write (connecting)')
      server, port = ((APNS_SERVER_SANDBOX_HOSTNAME 
                      if self.environment == 'sandbox'
                      else APNS_SERVER_HOSTNAME), APNS_SERVER_PORT)
      self.factory = self.clientProtocolFactory()
      context = self.getContextFactory()
      reactor.connectSSL(server, port, self.factory, context)
    
    client = self.factory.clientProtocol
    if self.debug:
      time.sleep(.750)
    if client:
      return client.sendMessage(notifications)
    else:      
      d = self.factory.deferred
      timeout = reactor.callLater(self.timeout, 
        lambda: d.called or d.errback(
          Exception('Notification timed out after %i seconds' % self.timeout)))
      def cancel_timeout(r):
        try: timeout.cancel()
        except: pass
        return r
      def send_cb(p):
        if self.debug:
          time.sleep(.750)
          p.sendMessage(notifications)
      d.addCallback(send_cb)
      d.addErrback(log_errback('apns-service-write'))
      d.addBoth(cancel_timeout)
      return d
  
  def read(self):
    "Connect to the feedback service and read all data."
    log.msg('APNSService read (connecting)')
    try:
      server, port = ((FEEDBACK_SERVER_SANDBOX_HOSTNAME 
                      if self.environment == 'sandbox'
                      else FEEDBACK_SERVER_HOSTNAME), FEEDBACK_SERVER_PORT)
      factory = self.feedbackProtocolFactory()
      context = self.getContextFactory()
      reactor.connectSSL(server, port, factory, context)
      factory.deferred.addErrback(log_errback('apns-feedback-read'))
      
      timeout = reactor.callLater(self.timeout,
        lambda: factory.deferred.called or factory.deferred.errback(
          Exception('Feedbcak fetch timed out after %i seconds' % self.timeout)))
      def cancel_timeout(r):
        try: timeout.cancel()
        except: pass
        return r
      
      factory.deferred.addBoth(cancel_timeout)
    except Exception, e:
      log.err('APNService feedback error initializing: %s' % str(e))
      raise
    return factory.deferred


class NotProvisioned(xmlrpc.Fault):
  pass


class APNSInterface(object):
  apps = app_ids
  le_id = 0
  distant_future = 9999999999*10

  def service(self, app_id):
    if app_id not in APNSInterface.apps:
      raise NotProvisioned(404, 'That app id (%s) is not provisioned' % app_id)
    return APNSInterface.apps[app_id]
  
  def provision(self, app_id, cert, env, timeout=15, log_disconnections=False, debug=False):
    if env not in ('production', 'sandbox'):
      raise ValueError('environment must be either production or sandbox')
    if not app_id in APNSInterface.apps:
      APNSInterface.apps[app_id] = APNSService(cert, env, timeout, log_disconnections, debug)

  def config(self, app_id, key, value):
    if key not in ('timeout', 'log_disconnections', 'debug'): raise KeyError
    self.service(app_id).__dict__[str(key)] = value

  def log(self, app_id):
    service = self.service(app_id)
    logs = service.log[:]
    service.log[:] = []
    return logs
  
  def notify(self, app_id, tokens, notifications):
    service = self.service(app_id)
    def _le_next_id():
      self.le_id += 1
      return self.le_id
    tokens = tokens if type(tokens) is list else [tokens]
    notifications = notifications if type(notifications) is list else [notifications]
    d = self.notify2(app_id, tokens, notifications,
        [self.distant_future]*len(tokens), 
        [_le_next_id() for i in xrange(len(tokens))])
    return d

  def notify2(self, app_id, tokens, notifications, expirys, idents):
    service = self.service(app_id)
    return service.write(
        encode_notifications2(
          [t.replace(' ', '') for t in (tokens if type(tokens) is list else [tokens])],
          notifications, expirys, idents, service.failure_callback()))

  def feedback(self, app_id):
    return self.service(app_id).read().addCallback(
      lambda r: decode_feedback(r))


class APNSServer(xmlrpc.XMLRPC, APNSInterface):
  def __init__(self):
    self.allowNone = True
    self.app_ids = APNSInterface.apps
    self.useDateTime = True
  
  def xmlrpc_provision(self, app_id, path_to_cert_or_cert, environment,
                       timeout=15, log_disconnections=False):
    """ Starts an APNSService for the this app_id and keeps it running
    
      Arguments:
          app_id                 the app_id to provision for APNS
          path_to_cert_or_cert   absolute path to the APNS SSL cert or a 
                                 string containing the .pem file
          environment            either 'sandbox' or 'production'
          timeout                seconds to timeout connection attempts
                                 to the APNS server
      Returns:
          None
    """
    try:
      self.provision(app_id, path_to_cert_or_cert, environment, timeout, log_disconnections)
    except ValueError:
      raise xmlrpc.Fault(401, 'Invalid environment provided `%s`. Valid '
                              'environments are `sandbox` and `production`' % (
                              environment,))
  
  def xmlrpc_config(self, app_id, key, value):
    """ Sets a configuration variable on a given APNSService for an app_id
    
    Currently working configuration keys and defaults:
      'log_disconnections': False
      'timeout':            15

      Arguments:
          app_id         the app_id to alter
          key            configuration key to change
          value          value of key
      Returns:
          None
    """
    try:
      self.config(app_id, key, value)
    except KeyError:
      raise xmlrpc.Fault(500, 'That configuration value does not exist %s => %s' % 
                         (key, str(value)))
  
  def xmlrpc_log(self, app_id):
    """ Returns and clears the APNSService log for a given app_id

    Current Types and info keys are:
      'ssl-connection-lost':
        'notifications': [list of notification dictionaries]
        'tokens':        [list ot token strings]
        'reason':        'stringified connection failure reason'
      
      Arguments:
          app_id        The app_id for which log messages will be returned
      Returns:
          List(List(String('type'), DateTime( event time ), {'infokeys': 'infovalues'}), ...)
    """

    return self.log(app_id)
  
  def xmlrpc_notify(self, app_id, token_or_token_list, aps_dict_or_list):
    """ Sends push notifications to the Apple APNS server. Multiple 
    notifications can be sent by sending pairing the token/notification
    arguments in lists [token1, token2], [notification1, notification2].
    
      Arguments:
          app_id                provisioned app_id to send to
          token_or_token_list   token to send the notification or a list of tokens
          aps_dict_or_list      notification dicts or a list of notifications
      Returns:
          None
    """
    
    try:
      d = self.notify(app_id, token_or_token_list, aps_dict_or_list)
    except APNSEncodeError, e:
      raise xmlrpc.Fault(500, 'There was an error encoding your notification: %s' % str(e))
    if d:
      def _finish_err(r):
        # so far, the only error that could really become of this
        # request is a timeout, since APNS simply terminates connectons
        # that are made unsuccessfully, which twisted will try endlessly
        # to reconnect to, we timeout and notifify the client
        raise xmlrpc.Fault(500, 'Connection to the APNS server could not be made.')
      return d.addCallbacks(lambda r: None, _finish_err)

  def xmlrpc_notify2(self, app_id, tokens, notifications, expirys, identifiers):
    """ Just like `notify' but uses the newer enhanced service which returns
    an uses an identifier for each notification (a long) and an expiration
    (a UTC timestamp in seconds) for each notification

      Arguments:
          app_id              provisioned app_id to send to
          tokens              a token or list of tokens to send to
          notifications       a notification or list of notifications (same length as tokens)
          expirys             expiration period for these notifications
          identifiers         identifiers for each notification
      Returns:
          None
    """

    try:
      d = self.notify2(app_id, tokens, notifications, expirys, identifiers)
    except APNSEncodeError, e:
      raise xmlrpc.Fault(500, 'There was an error encoding your notifications: %s' % str(e))
    if d:
      def _done_sending_err(r):
        raise xmlrpc.Fault(500, 'Connection to the APNS Server could not be made.')
      return d.addCallbacks(lambda r: None, _done_sending_err) 
  
  def xmlrpc_feedback(self, app_id):
    """ Queries the Apple APNS feedback server for inactive app tokens. Returns
    a list of tuples as (datetime_went_dark, token_str).
    
      Arguments:
          app_id   the app_id to query
      Returns:
          Feedback tuples like (datetime_expired, token_str)
    """
    
    return self.feedback(app_id)


from twisted.web.resource import NoResource
import json


def json_response(F):
  def _wrap(self, request):
    R = F(self, request)
    request.setHeader('Content-Type', 'application/json')
    if isinstance(R, defer.Deferred):
      return R.addCallback(json.dumps)
    return json.dumps(R)
  return _wrap


def application_v1(app_id, app):
  return {
      'app_id': app_id,
      'environment': app.environment,
      'cert': app.cert_path,
      'timeout': app.timeout,
      'log_disconnections': app.log_disconnections,
      'log': app.log
  }

class APNSApplicationResource(resource.Resource):
  def __init__(self, *args):
    resource.Resource.__init__(self)
    self.app = args[0]
    self.app_id = args[1]
    self.args = args


class APNSAppRootResource(APNSApplicationResource):
  def getChild(self, name, request):
    print 'get child', name, str(request)
    if name == 'feedback':
      return APNSAppFeedbackResource(*self.args)
    return self
  
  @json_response
  def render_GET(self, request):
    return application_v1(self.app_id, self.app)


class APNSAppFeedbackResource(APNSApplicationResource):
  @json_response
  def render_GET(self, request):
    return self.feedback(self.app_id)


class APNSAppNotificationResource(APNSApplicationResource):
  @json_response
  def render_POST(self, request):
    return 'not implemented'


class APNSAppsResource(resource.Resource, APNSInterface):
  def getChild(self, name, request):
    if name == '': return self
    try:
      return APNSApplicationResource(name, self.service(name))
    except NotProvisioned:
      return NoResource()

  @json_response
  def render_POST(self, request):
    self._provision(request)
    return [application_v1(app_id, self.service(app_id))
      for app_id in request.args['app_id']]
  
  @json_response
  def render_GET(self, request):
    face = APNSInterface()
    return [application_v1(k, face.service(k)) for k in APNSInterface.apps.keys()]
  
  def _provision(self, request):
    face = APNSInterface()
    for i in xrange(len(request.args['app_id'])):
      face.provision(
          request.args['app_id'][i],
          request.args['cert'][i],
          request.args['environment'][i],
          int(request.args['timeout'][i]),
          bool(request.args['log_disconnections'][i]))


class APNSRestServer(resource.Resource):
  def getChild(self, name, request):
    log.msg('APNSRestServer ' + name)
    if name == 'api':
      return self
    if name == 'v1':
      return self
    if name == 'apps':
      return APNSAppsResource()
    return self

  def render_GET(self, request):
    return "Hello wurld"


def encode_notifications(tokens, notifications, on_failure):
  """ Returns the encoded bytes of tokens and notifications
  
        tokens          a list of tokens or a string of only one token
        notifications   a list of notifications or a dictionary of only one
  """
  
  fmt = "!BH32sH%ds"
  structify = lambda t, p: struct.pack(fmt % len(p), 0, 32, t, len(p), p)
  binaryify = lambda t: t.decode('hex')
  if type(notifications) is dict and type(tokens) in (str, unicode):
    tokens, notifications = ([tokens], [notifications])
  if type(notifications) is list and type(tokens) is list:
    return NotificationString(
      ''.join(map(lambda y: structify(*y), ((binaryify(t), json.dumps(p, separators=(',',':')))
                                            for t, p in zip(tokens, notifications)))),
                              on_failure=on_failure, notifications=notifications, tokens=tokens)


class APNSEncodeError(Exception): pass


def encode_notifications2(tokens, notifications, expirys, identifiers, on_failure):
  fmt = '!BLLH32sH%ds'
  structify = lambda t, e, i, p: struct.pack(fmt % len(p), 1, e, i, 32, t, len(p), p)
  binaryify = lambda t: t.decode('hex')
  def binaryify(t):
    try:
      return t.decode('hex')
    except TypeError, e:
      raise APNSEncodeError('token "%s" could not be decoded: %s' % (str(t), str(e)))
  _list = lambda v: v if type(v) is list else [v]
  return NotificationString(
      ''.join(map(lambda y: structify(*y), (
        (binaryify(t), e, i, json.dumps(p, separators=(',',':')))
           for t, e, i, p in zip(_list(tokens),
                                 map(int, _list(expirys)), map(int, _list(identifiers)),
                                 _list(notifications))))),
          on_failure=on_failure, notifications=notifications,
          tokens=tokens, expirys=expirys, identifiers=identifiers)

def decode_feedback(binary_tuples):
  """ Returns a list of tuples in (datetime, token_str) format 
  
        binary_tuples   the binary-encoded feedback tuples
  """
  
  fmt = '!lh32s'
  size = struct.calcsize(fmt)
  with StringIO(binary_tuples) as f:
    return [(datetime.datetime.fromtimestamp(ts), binascii.hexlify(tok))
            for ts, toklen, tok in (struct.unpack(fmt, tup) 
                              for tup in iter(lambda: f.read(size), ''))]

def decode_error_packet(packet):
  fmt = '!Bbl'
  cmd, code, ident = struct.unpack(fmt, packet)
  print 'decode ', cmd, code, ident
  if code in APNS_STATUS_CODES:
    return (code, APNS_STATUS_CODES[code], ident)

def log_errback(name):
  def _log_errback(err, *args):
    log.err('errback in %s : %s' % (name, str(err)))
    return err
  return _log_errback
