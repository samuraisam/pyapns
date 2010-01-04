from __future__ import with_statement
import _json as json
import base64
import struct
import logging
import binascii
import datetime
from cStringIO import StringIO
from OpenSSL import SSL, crypto
from twisted.internet import reactor, defer
from twisted.internet.protocol import (
  ReconnectingClientFactory, ClientFactory, Protocol, ServerFactory)
from twisted.internet.ssl import ClientContextFactory
from twisted.application import internet, service
from twisted.protocols.basic import LineReceiver
from twisted.python import log
from zope.interface import Interface, implements
from twisted.web import xmlrpc


APNS_SERVER_SANDBOX_HOSTNAME = "gateway.sandbox.push.apple.com"
APNS_SERVER_HOSTNAME = "gateway.push.apple.com"
APNS_SERVER_PORT = 2195
FEEDBACK_SERVER_SANDBOX_HOSTNAME = "feedback.sandbox.push.apple.com"
FEEDBACK_SERVER_HOSTNAME = "feedback.push.apple.com"
FEEDBACK_SERVER_PORT = 2196

app_ids = {} # {'app_id': APNSService()}


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
    self.factory.addClient(self)
  
  def sendMessage(self, msg):
    log.msg('APNSProtocol sendMessage msg=%s' % binascii.hexlify(msg))
    return self.transport.write(msg)
  
  def connectionLost(self, reason):
    log.msg('APNSProtocol connectionLost')
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
    self.deferred.callback(self.io.getValue())
    io.close()


class APNSFeedbackClientFactory(ClientFactory):
  protocol = APNSFeedbackHandler
  
  def __init__(self):
    self.deferred = defer.Deferred()
  
  def buildProtocol(self, addr):
    p = self.protocol()
    p.factory = self
    p.deferred = self.deferred
    p.io = StringIO
    p.setRawMode()
    return p
  
  def startedConnecting(self, connector):
    log.msg('APNSFeedbackClientFactory startedConnecting')
  
  def clientConnectionLost(self, connector, reason):
    log.msg('APNSFeedbackClientFactory clientConnectionLost reason=%s' % reason)
    ReconnectingClientFactory.clientConnectionLost(self, connector, reason)
  
  def clientConnectionFailed(self, connector, reason):
    log.msg('APNSFeedbackClientFactory clientConnectionFailed reason=%s' % reason)
    ReconnectingClientFactory.clientConnectionLost(self, connector, reason)


class APNSClientFactory(ReconnectingClientFactory):
  protocol = APNSProtocol
  
  def __init__(self):
    self.clientProtocol = None
    self.deferred = defer.Deferred()
    self.deferred.addErrback(log_errback('APNSClientFactory__init__'))
  
  def addClient(self, p):
    self.clientProtocol = p
    self.deferred.callback(p)
  
  def removeClient(self, p):
    self.clientProtocol = None
    self.deferred = defer.Deferred()
    self.deferred.addErrback(log_errback('APNSClientFactoryremoveClient'))
  
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
    ReconnectingClientFactory.clientConnectionLost(self, connector, reason)


class APNSService(service.Service):
  """ A Service that sends notifications and receives 
  feedback from the Apple Push Notification Service
  """
  implements(IAPNSService)
  clientProtocolFactory = APNSClientFactory
  feedbackProtocolFactory = APNSFeedbackClientFactory
  
  def __init__(self, cert_path, environment):
    log.msg('APNSService __init__')
    self.factory = None
    self.environment = environment
    self.cert_path = cert_path
    self.raw_mode = False
  
  def getContextFactory(self):
    return APNSClientContextFactory(self.cert_path)
  
  def write(self, notifications):
    "Connect to the APNS service and send notifications"
    if not self.factory:
      log.msg('APNSService write (connecting)')
      server, port = ((APNS_SERVER_SANDBOX_HOSTNAME 
                      if self.environment == 'sandbox'
                      else APNS_SERVER_HOSTNAME), APNS_SERVER_PORT)
      self.factory = self.clientProtocolFactory()
      context = self.getContextFactory()
      reactor.connectSSL(server, port, self.factory, context)
    
    client = self.factory.clientProtocol
    if client:
      return client.sendMessage(notifications)
    else:
      d = self.factory.deferred
      d.addCallback(lambda p: p.sendMessage(notifications))
      d.addErrback(log_errback('apns-service-write'))
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
    except Exception, e:
      log.err('APNService feedback error initializing: %s' % str(e))
      raise
    return factory.deferred


class APNSServer(xmlrpc.XMLRPC):
  def __init__(self):
    self.allowNone = True
    self.app_ids = app_ids
  
  def apns_service(self, app_id):
    if app_id not in app_ids:
      raise xmlrpc.Fault(404, 'The app_id specified has not been provisioned.')
    return self.app_ids[app_id]
  
  def xmlrpc_provision(self, app_id, path_to_cert_or_cert, environment):
    """ Starts an APNSService for the this app_id and keeps it running
    
      Arguments:
          app_id                 the app_id to provision for APNS
          path_to_cert_or_cert   absolute path to the APNS SSL cert or a 
                                 string containing the .pem file
          environment            either 'sandbox' or 'production'
      Returns:
          None
    """
    
    if not app_id in self.app_ids:
      self.app_ids[app_id] = APNSService(path_to_cert_or_cert, environment)
  
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
    
    self.apns_service(app_id).write(
      encode_notifications(
        [t.replace(' ', '') for t in token_or_token_list] 
          if (type(token_or_token_list) is list)
          else token_or_token_list.replace(' ', ''),
        aps_dict_or_list))
  
  def xmlrpc_feedback(self, app_id):
    """ Queries the Apple APNS feedback server for inactive app tokens. Returns
    a list of tuples as (datetime_went_dark, token_str).
    
      Arguments:
          app_id   the app_id to query
      Returns:
          Feedback tuples like (datetime_expired, token_str)
    """
    
    return self.apns_service(app_id).read().addCallback(
      lambda r: decode_feedback(r))


def encode_notifications(tokens, notifications):
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
    return ''.join(map(lambda y: structify(*y), ((binaryify(t), json.dumps(p))
                                    for t, p in zip(tokens, notifications))))

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

def log_errback(name):
  def _log_errback(err, *args):
    log.err('errback in %s : %s' % (name, str(err)))
    return err
  return _log_errback
