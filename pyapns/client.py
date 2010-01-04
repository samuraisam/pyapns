import xmlrpclib
import threading

OPTIONS = {'CONFIGURED': False}

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


def provision(app_id, path_to_cert, environment, callback=None):
  args = [app_id, path_to_cert, environment]
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

def feedback(app_id, callback=None):
  args = [app_id]
  if callback is None:
    return _xmlrpc_thread('feedback', args, lambda r: r)
  t = threading.Thread(target=_xmlrpc_thread, args=['feedback', args, callback])
  t.daemon = True
  t.start()

def _xmlrpc_thread(method, args, callback):
  if not configure({}):
    raise APNSNotConfigured('APNS Has not been configured.')
  proxy = xmlrpclib.ServerProxy(OPTIONS['HOST'], allow_none=True, use_datetime=True)
  try:
    parts = method.strip().split('.')
    for part in parts:
      proxy = getattr(proxy, part)
    return callback(proxy(*args))
  except xmlrpclib.Fault, e:
    if e.faultCode == 404:
      raise UnknownAppID
    raise

