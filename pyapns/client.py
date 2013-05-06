import xmlrpclib
import threading
import httplib
import functools
from sys import hexversion
import requests
from pyapns import _json as json
from pyapns.model import Notification, DisconnectionEvent


class ClientError(Exception):
    def __init__(self, message, response):
        super(ClientError, self).__init__(message)
        self.message = message
        self.response = response


class Client(object):
    @property
    def connection(self):
        con = getattr(self, '_connection', None)
        if con is None:
            con = self._connection = requests.Session()
        return con

    def __init__(self, host='http://localhost', port=8088, timeout=20):
        self.host = host.strip('/')
        self.port = port
        self.timeout = timeout

    def provision(self, app_id, environment, certificate, timeout=15):
        """
        Tells the pyapns server that we want set up an app to receive 
        notifications from us.

        :param app_id: An app id, you can use anything but it's
        recommended to just use the bundle identifier used in your app.
        :type app_id: string
        
        :param environment: Which environment are you using? This value
        must be either "production" or "sandbox".
        :type environment: string

        :param certificate: A path to a encoded, password-free .pem file 
        on the pyapns host. This must be a path local to the host! You 
        can also read an entire .pem file in and send it in this value 
        as well.
        :type certificate: string

        :returns: Dictionary-representation of the App record
        :rtype: dict
        """
        status, resp = self._request(
            'POST', 'apps/{}/{}'.format(app_id, environment),
            data={'certificate': certificate, 'timeout': timeout}
        )
        if status != 201:
            raise ClientError('Unable to provision app id', resp)
        return resp['response'] 

    def notify(self, app_id, environment, notifications):
        """
        Sends notifications to clients via the pyapns server. The 
        `app_id` and `environment` must be previously provisioned 
        values--either by using the :py:meth:`provision` method or 
        having been bootstrapped on the server.

        `notifications` is a list of notification dictionaries that all
        must have the following keys:

            *  `payload` is the actual notification dict to be jsonified
            *  `token` is the hexlified device token you scraped from 
                the client
            *  `identifier` is a unique id specific to this id. for this 
                you may use any value--pyapns will generate its own 
                internal ID to track it. The APN gateway only allows for
                this to be 4 bytes.
            *  `expiry` is how long the notification should be retried 
                for if for some reason the apple servers can not contact
                the device

        You can also construct a :py:class:`Notification` object--the
        dict and class representations are interchangable here.

        :param app_id: Which app id to use
        :type app_id: string

        :param environmenet: The environment for the app_id
        :type environment: string

        :param notifications: A list of notification dictionaries
        (see the discussion above)
        :type notifications: list

        :returns: Empty response--this method doesn't return anything
        :rtype: dict 
        """
        notes = []
        for note in notifications:
            if isinstance(note, dict):
                notes.append(Notification.from_simple(note))
            elif isinstance(note, Notification):
                notes.append(note)
            else:
                raise ValueError('Unknown notification: {}'.format(repr(note)))
        data = [n.to_simple() for n in notes]

        status, resp = self._request(
            'POST', 'apps/{}/{}/notifications'.format(app_id, environment), 
            data=data
        )
        if status != 201:
            raise ClientError('Could not send notifications', resp)
        return resp['response']

    def feedback(self, app_id, environment):
        """
        Gets the from the APN feedback service. These are tokens that 
        Apple considers to be "dead" - that you should no longer attempt
        to deliver to.

        Returns a list of dictionaries with the keys:

            * `timestamp` - the UTC timestamp when Apple determined the
               token to be dead
            * `token` - the hexlified version of the token

        :param app_id: Which app id to use
        :type app_id: string

        :param environmenet: The environment for the app_id
        :type environment: string

        :rtrype: list
        """
        status, feedbacks = self._request(
            'GET', 'apps/{}/{}/feedback'.format(app_id, environment)
        )
        if status != 200:
            raise ClientError('Could not fetch feedbacks', feedbacks)
        return feedbacks['response']

    def disconnections(self, app_id, environment):
        """
        Retrieves a list of the 5000 most recent disconnection events 
        recorded by pyapns. Each time apple severs the connection with 
        pyapns it will try to send back an error packet describing which
        notification caused the error and the error that occurred.

        :param app_id: Which app id to use
        :type app_id: string

        :param environmenet: The environment for the app_id
        :type environment: string

        :rtype: list
        """
        status, disconnects = self._request(
            'GET', 'apps/{}/{}/disconnections'.format(app_id, environment)
        )
        if status != 200:
            raise ClientError('Could not retrieve disconnections', disconnects)
        ret = []
        for evt in disconnects['response']:
            ret.append(DisconnectionEvent.from_simple(evt))
        return ret

    def _request(self, method, path, args=None, data=None):
        url = '{}:{}/{}'.format(self.host, self.port, path)
        kwargs = {'timeout': self.timeout}
        if args is not None:
            kwargs['params'] = args
        if data is not None:
            kwargs['data'] = json.dumps(data)

        func = getattr(self.connection, method.lower())
        resp = func(url, **kwargs)
        if resp.headers['content-type'].startswith('application/json'):
            resp_data = json.loads(resp.content)
        else:
            resp_data = None
        return resp.status_code, resp_data


## OLD XML-RPC INTERFACE ------------------------------------------------------

OPTIONS = {'CONFIGURED': False, 'TIMEOUT': 20}


def configure(opts):
    if not OPTIONS['CONFIGURED']:
        try:  # support for django
            import django.conf
            OPTIONS.update(django.conf.settings.PYAPNS_CONFIG)
            OPTIONS['CONFIGURED'] = True
        except:
            pass
        if not OPTIONS['CONFIGURED']:
            try:  # support for programatic configuration
                OPTIONS.update(opts)
                OPTIONS['CONFIGURED'] = True
            except:
                pass
        if not OPTIONS['CONFIGURED']:
            try:  # pylons support
                import pylons.config
                OPTIONS.update({'HOST': pylons.config.get('pyapns_host')})
                try:
                    OPTIONS.update(
                        {'TIMEOUT': int(pylons.config.get('pyapns_timeout'))})
                except:
                    pass  # ignore, an optional value
                OPTIONS['CONFIGURED'] = True
            except:
                pass
        # provision initial app_ids
        if 'INITIAL' in OPTIONS:
            for args in OPTIONS['INITIAL']:
                provision(*args)
    return OPTIONS['CONFIGURED']


class UnknownAppID(Exception):
    pass


class APNSNotConfigured(Exception):
    pass


def reprovision_and_retry(func):
    """
    Wraps the `errback` callback of the API functions, automatically trying to
    re-provision if the app ID can not be found during the operation. If that's
    unsuccessful, it will raise the UnknownAppID error.
    """
    @functools.wraps(func)
    def wrapper(*a, **kw):
        errback = kw.get('errback', None)
        if errback is None:
            def errback(e):
                raise e

        def errback_wrapper(e):
            if isinstance(e, UnknownAppID) and 'INITIAL' in OPTIONS:
                try:
                    for initial in OPTIONS['INITIAL']:
                        provision(
                            *initial)  # retry provisioning the initial setup
                    func(*a, **kw)  # and try the function once more
                except Exception, new_exc:
                    errback(new_exc)  # throwing the new exception
            else:
                errback(e)  # not an instance of UnknownAppID - nothing we can do here
        kw['errback'] = errback_wrapper
        return func(*a, **kw)
    return wrapper


def default_callback(func):
    @functools.wraps(func)
    def wrapper(*a, **kw):
        if 'callback' not in kw:
            kw['callback'] = lambda c: c
        return func(*a, **kw)
    return wrapper


@default_callback
@reprovision_and_retry
def provision(app_id, path_to_cert, environment, timeout=15, async=False,
              callback=None, errback=None):
    args = [app_id, path_to_cert, environment, timeout]
    f_args = ['provision', args, callback, errback]
    if not async:
        return _xmlrpc_thread(*f_args)
    t = threading.Thread(target=_xmlrpc_thread, args=f_args)
    t.daemon = True
    t.start()


@default_callback
@reprovision_and_retry
def notify(app_id, tokens, notifications, async=False, callback=None,
           errback=None):
    args = [app_id, tokens, notifications]
    f_args = ['notify', args, callback, errback]
    if not async:
        return _xmlrpc_thread(*f_args)
    t = threading.Thread(target=_xmlrpc_thread, args=f_args)
    t.daemon = True
    t.start()


@default_callback
@reprovision_and_retry
def feedback(app_id, async=False, callback=None, errback=None):
    args = [app_id]
    f_args = ['feedback', args, callback, errback]
    if not async:
        return _xmlrpc_thread(*f_args)
    t = threading.Thread(target=_xmlrpc_thread, args=f_args)
    t.daemon = True
    t.start()


def _xmlrpc_thread(method, args, callback, errback=None):
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
            e = UnknownAppID()
        if errback is not None:
            errback(e)
        else:
            raise e


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
