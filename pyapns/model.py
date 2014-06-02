import struct
import datetime
import calendar
from collections import defaultdict, deque
from pyapns.server import APNSService, decode_feedback
from pyapns import _json as json


class NoSuchAppException(Exception):
    pass


class AppRegistry(object):
    # stored as [app_name][environment] = App()
    apps = defaultdict(dict)

    @classmethod
    def all_apps(cls):
        for envs in cls.apps.values():
            for e in envs.values():
                yield e

    @classmethod
    def get(cls, name, environment):
        if name not in cls.apps or environment not in cls.apps[name]:
            raise NoSuchAppException()
        else:
            return cls.apps[name][environment]

    @classmethod
    def put(cls, name, environment, cert, **attrs):
        app = App(name, environment, cert, **attrs)
        cls.apps[name][environment] = app
        return app


class App(object):
    @property
    def connection(self):
        """
        The pyapns.server.APNSService object - a kind of lazy connection object
        """
        r = getattr(self, '_connection', None)
        if r is None:
            r = self._connection = APNSService(
                self.cert, self.environment, self.timeout, 
                on_failure_received=self._on_apns_error
            )
        return r


    def __init__(self, name, environment, cert_file, timeout=15):
        self.name = name
        self.environment = environment 
        self.cert = cert_file
        self.timeout = timeout
        self.disconnections_to_keep = 5000
        self.recent_notifications_to_keep = 10000

        self.disconnections = deque(maxlen=self.disconnections_to_keep)

        self.recent_notification_idents = deque() # recent external notification idents
        self.recent_notifications = {} # maps external idents to notifications

        self.internal_idents = {} # maps internal idents to external idents
        self.ident_counter = 0

    def notify(self, notifications):
        """
        Send some notifications to devices using the APN gateway.

            * `notifications` is a list of `Notification` objects.

            * Returns a deferred that will be fired when the connection is 
              opened if the connection was previously closed, otherwise just
              returns None

        If when sending a notification and the connection to the APN gateway
        is lost, we will read back the error message sent by Apple (the 
        "enhanced" format) and try to figure out which notification is was
        the offending one. If found, it will be appended to the list of recent
        disconnections accessible with `disconnections()`.

        In order to figure out which notification was offensive in the case of
        a disconnect, we must keep the last N notifications sent over the 
        socket, in right now that number is 10000.

        We will only store the most recent 5000 disconnections. You should 
        probably pull the notifications at least every day, perhaps more 
        frequently for high-volume installations.
        """
        self.remember_recent_notifications(notifications)
        return self.connection.write(encode_notifications(notifications))

    def feedback(self):
        """
        Gets a list of tokens that are identified by Apple to be invalid.
        This clears the backlog of invalid tokens on Apple's servers so do
        your best to not loose it!
        """
        # this is for testing feedback parsing w/o draining your feedbacks
        # from twisted.internet.defer import Deferred
        # import struct
        # d = Deferred()
        # d.callback(struct.pack('!lh32s', 42, 32, 'e6e9cf3d0405ee61eac9552a5a17bff62a64a131d03a2e1638d06c25e105c1e5'.decode('hex')))
        d = self.connection.read()
        def decode(raw_feedback):
            feedbacks = decode_feedback(raw_feedback)
            return [
                {
                    'type': 'feedback',
                    'timestamp': (
                        float(calendar.timegm(ts.timetuple())) 
                        + float(ts.microsecond) / 1e6
                    ),
                    'token': tok
                } for ts, tok in feedbacks]
        d.addCallback(decode)
        return d

    def to_simple(self):
        return {
            'name': self.name,
            'environment': self.environment,
            'certificate': self.cert,
            'timeout': self.timeout,
            'type': 'app'
        }

    def _on_apns_error(self, raw_error):
        self.remember_disconnection(
            DisconnectionEvent.from_apn_wire_format(raw_error)
        )

    def get_next_ident(self):
        """
        Available range is between 0x0 and 0xffff because the 'ident' field
        of the APN packet is a ushort
        """
        if self.ident_counter > 0xffff:
            self.ident_count = 0
        else:
            self.ident_counter += 1
        return self.ident_counter

    def remember_recent_notifications(self, notifications):
        for note in reversed(notifications):
            # check whether we already saw this notification, ignore if so
            existing_note = self.recent_notifications.get(note.identifier, None)
            if existing_note is not None:
                # they have the same external ident so they can share the same interna
                note.internal_identifier = existing_note.internal_identifier
                continue

            # make room for a notification if the remembered notifications is full
            if len(self.recent_notification_idents) >= self.recent_notifications_to_keep:
                removed_ident = self.recent_notification_idents.popleft()
                removed_note = self.recent_notifications.pop(removed_ident)
                self.internal_idents.pop(removed_note.internal_identifier)

            # create a new internal identifier and map the notification to it
            internal_ident = self.get_next_ident()
            self.recent_notification_idents.append(note.identifier)
            self.recent_notifications[note.identifier] = note
            self.internal_idents[internal_ident] = note.identifier
            note.internal_identifier = internal_ident

    def remember_disconnection(self, disconnection):
        known_ident = self.internal_idents.get(disconnection.identifier, None)
        if known_ident is not None and known_ident in self.recent_notifications:
            disconnection.offending_notification = self.recent_notifications[known_ident]
        self.disconnections.append(disconnection)


def encode_notifications(notifications):
    return ''.join([n.to_apn_wire_format() for n in notifications])


class Notification(object):
    """
    A single notification being sent to the APN service.

    The fields are described as follows:

        *  `payload` is the actual notification dict to be jsonified
        *  `token` is the hexlified device token you scraped from the client
        *  `identifier` is a unique id specific to this id. for this you
            may use a UUID--but we will generate our own internal ID to track
            it. The APN gateway only allows for this to be 4 bytes.
        *  `expiry` is how long the notification should be retried for if
            for some reason the apple servers can not contact the device
    """

    __slots__ = ('token', 'payload', 'expiry', 'identifier', 'internal_identifier')

    def __init__(self, token=None, payload=None, expiry=None, identifier=None, 
                 internal_identifier=None):
        self.token = token
        self.payload = payload
        self.expiry = expiry
        self.identifier = identifier
        self.internal_identifier = internal_identifier

    @classmethod
    def from_simple(cls, data, instance=None):
        note = instance or cls()
        note.token = data['token']
        note.payload = data['payload']
        note.expiry = int(data['expiry'])
        note.identifier = data['identifier']
        return note

    def to_simple(self):
        return {
            'type': 'notification',
            'expiry': self.expiry,
            'identifier': self.identifier,
            'payload': self.payload,
            'token': self.token
        }

    def to_apn_wire_format(self):
        fmt = '!BLLH32sH%ds'
        structify = lambda t, i, e, p: struct.pack(fmt % len(p), 1, i, e, 32, 
                                                   t, len(p), p)
        binaryify = lambda t: t.decode('hex')
        def binaryify(t):
            try:
                return t.decode('hex')
            except TypeError, e:
                raise ValueError(
                    'token "{}" could not be decoded: {}'.format(str(t), str(e)
                ))

        encoded_payload = json.dumps(self.payload,
                                     separators=(',', ':')).encode('utf-8')
        return structify(binaryify(self.token), self.internal_identifier, 
                         self.expiry, encoded_payload)

    def __repr__(self):
        return u'<Notification token={} identifier={} expiry={} payload={}>'.format(
            self.token, self.identifier, self.expiry, self.payload
        )


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
    10: 'Shutdown',
    255: 'None (unknown)'
}


class DisconnectionEvent(object):
    __slots__ = ('code', 'offending_notification', 'timestamp', 'identifier')

    def __init__(self):
        self.code = None
        self.offending_notification = None
        self.timestamp = None
        self.identifier = None

    def to_simple(self):
        return {
            'type': 'disconnection',
            'code': self.code,
            'internal_identifier': self.identifier,
            'offending_notification': (
                self.offending_notification.to_simple() 
                if self.offending_notification is not None else None
            ),
            'timestamp': (
                float(calendar.timegm(self.timestamp.timetuple())) 
                + float(self.timestamp.microsecond) / 1e6
            ),
            'verbose_message': APNS_STATUS_CODES[self.code]
        }

    @classmethod
    def from_simple(cls, data):
        evt = cls()
        evt.code = data['code']
        evt.identifier = data['internal_identifier']
        evt.timestamp = datetime.datetime.utcfromtimestamp(data['timestamp'])
        if 'offending_notification' in data:
            evt.offending_notification = \
                Notification.from_simple(data['offending_notification'])
        return evt

    @classmethod
    def from_apn_wire_format(cls, packet):
        fmt = '!Bbl'
        cmd, code, ident = struct.unpack(fmt, packet)

        evt = cls()
        evt.code = code
        evt.timestamp = datetime.datetime.utcnow()
        evt.identifier = ident
        return evt

    def __repr__(self):
        return '<DisconnectionEvent internalIdent={} error="{}"" notification={}>'.format(
            self.identifier, APNS_STATUS_CODES[self.code], 
            self.offending_notification
        )

