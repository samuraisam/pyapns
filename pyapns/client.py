import xmlrpclib
import threading
import httplib
from sys import hexversion

OPTIONS = {'CONFIGURED': False, 'TIMEOUT': 20}

def configure(opts):
  if not OPTIONS['CONFIGURED']:
    try: # support for django
      import django.conf
      OPTIONS.update(django.conf.settings.PYAPNS_CONFIG)
      OPTIONS['CONFIGURED'] = True
    except:
      pass
    if not OPTIONS['CONFIGURED']:
      try: # support for programatic configuration
        OPTIONS.update(opts)
        OPTIONS['CONFIGURED'] = True
      except:
        pass
    if not OPTIONS['CONFIGURED']:
      try: # pylons support
        import pylons.config
        OPTIONS.update({'HOST': pylons.config.get('pyapns_host')})
        try:
          OPTIONS.update({'TIMEOUT': int(pylons.config.get('pyapns_timeout'))})
        except:
          pass # ignore, an optional value
        OPTIONS['CONFIGURED'] = True
      except:
        pass
    # provision initial app_ids
    if 'INITIAL' in OPTIONS:
      for args in OPTIONS['INITIAL']:
        provision(*args)
  return OPTIONS['CONFIGURED']


class UnknownAppID(Exception): pass
class APNSNotConfigured(Exception): pass


def provision(app_id, path_to_cert, environment, timeout=15, log_disconnections=False, debug=False, callback=None):
  if getattr(log_disconnections, '__call__', None) is not None:
    raise NameError("callback is no longer the 4th argument. use keyword arguments instead")
  args = [app_id, path_to_cert, environment, timeout, log_disconnections]
  if callback is None:
    return _xmlrpc_thread('provision', args, lambda r: r)
  t = threading.Thread(target=_xmlrpc_thread, args=['provision', args, callback])
  t.daemon = True
  t.start()

def notify(app_id, tokens, notifications, callback=None):
  args = [app_id, tokens, notifications]
  if callback is None:
    return _xmlrpc_thread('notify', args, lambda r: r)
  t = threading.Thread(target=_xmlrpc_thread, args=['notify', args, callback])
  t.daemon = True
  t.start()

def notify2(app_id, tokens, notifications, expirys, identifiers, callback=None):
  args = [app_id, tokens, notifications, expirys, identifiers]
  if callback is None:
    return _xmlrpc_thread('notify2', args, lambda r: r)
  t = threading.Thread(target=_xmlrpc_thread, args=['notify2', args, callback])
  t.daemon = True
  t.start()

def feedback(app_id, callback=None):
  args = [app_id]
  if callback is None:
    return _xmlrpc_thread('feedback', args, lambda r: r)
  t = threading.Thread(target=_xmlrpc_thread, args=['feedback', args, callback])
  t.daemon = True
  t.start()

def config(app_id, key, value, callback=None):
  args = [app_id, key, value]
  if callback is None:
    return _xmlrpc_thread('config', args, lambda r: r)
  t = threading.Thread(target=_xmlrpc_thread, args=['config', args, callback])
  t.daemon = True
  t.start()

def log(app_id, callback=None):
  args = [app_id]
  if callback is None:
    return _xmlrpc_thread('log', args, lambda r: r)
  t = threading.Thread(target=_xmlrpc_thread, args=['log', args, callback])
  t.daemon = True
  t.start()

def _xmlrpc_thread(method, args, callback):
  if not configure({}):
    raise APNSNotConfigured('APNS Has not been configured.')
  proxy = ServerProxy(OPTIONS['HOST'], allow_none=True, use_datetime=True,
                      timeout=OPTIONS['TIMEOUT'])
  try:
    parts = method.strip().split('.')
    for part in parts:
      proxy = getattr(proxy, part)
    return callback(proxy(*args))
  except xmlrpclib.Fault, e:
    if e.faultCode == 404:
      raise UnknownAppID
    raise


## --------------------------------------------------------------
## Thank you Volodymyr Orlenko:
## http://blog.bjola.ca/2007/08/using-timeout-with-xmlrpclib.html
## --------------------------------------------------------------

def ServerProxy(url, *args, **kwargs):
  t = TimeoutTransport()
  t.timeout = kwargs.pop('timeout', 20)
  kwargs['transport'] = t
  return xmlrpclib.ServerProxy(url, *args, **kwargs)

class TimeoutTransport(xmlrpclib.Transport):
  def make_connection(self, host):
    if hexversion < 0x02070000:
        conn = TimeoutHTTP(host)
        conn.set_timeout(self.timeout)
    else:
        conn = TimeoutHTTPConnection(host)
        conn.timeout = self.timeout
    return conn

class TimeoutHTTPConnection(httplib.HTTPConnection):
  def connect(self):
    httplib.HTTPConnection.connect(self)
    self.sock.settimeout(self.timeout)
  
class TimeoutHTTP(httplib.HTTP):
  _connection_class = TimeoutHTTPConnection
  
  def set_timeout(self, timeout):
    self._conn.timeout = timeout
  
