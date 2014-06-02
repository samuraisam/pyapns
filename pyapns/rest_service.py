import calendar
from twisted.web.resource import Resource, NoResource
from twisted.web.server import NOT_DONE_YET
from twisted.python import log
from pyapns.model import AppRegistry, NoSuchAppException, Notification
from pyapns import _json as json


PRODUCTION = 'production'
SANDBOX = 'sandbox'
ENVIRONMENTS = (PRODUCTION, SANDBOX)


class ErrorResource(Resource):
    isLeaf = True

    def __init__(self, code, message, **attrs):
        Resource.__init__(self)
        self.code = code
        self.message = message 
        self.attrs = attrs

    def render(self, request):
        request.setResponseCode(self.code)
        request.setHeader('content-type', 'application/json; charset=utf-8')
        return json.dumps({
            'code': self.code,
            'message': self.message,
            'type': 'error',
            'args': self.attrs
        })


def json_response(data, request, status_code=200):
    request.setResponseCode(status_code)
    request.setHeader('content-type', 'application/json; charset=utf-8')
    return json.dumps({'code': status_code, 'response': data})


# to handle /apps/<app name>
class AppRootResource(Resource):
    def getChild(self, name, request):
        if name == '':
            return self
        else:
            return AppResource(name)

    def render_GET(self, request):
        apps = [app.to_simple() for app in AppRegistry.all_apps()]
        return json_response(apps, request)


# to handle /apps/<app name>/<environment name>
class AppResource(Resource):
    def __init__(self, app_name):
        Resource.__init__(self)
        self.app_name = app_name

    def getChild(self, name, request):
        if name in ENVIRONMENTS:
            return AppEnvironmentResource(self.app_name, name)
        else:
            return ErrorResource(
                404, 'Environment must be either `production` or `sandbox`',
                environment=name, app=self.app_name
            )


# to handle /apps/<app name>/<environment name>/(<resource>)?
class AppEnvironmentResource(Resource):
    def __init__(self, app_name, environment):
        Resource.__init__(self)
        self.app_name = app_name
        self.environment = environment

    def getChild(self, name, request):
        if name == '':
            return self

        try:
            app = AppRegistry.get(self.app_name, self.environment)
        except NoSuchAppException:
            return ErrorResource(
                404, 'No app registered under that name and environment',
                name=self.app_name,
                environment=name
            )
        else:
            if name == 'feedback':
                return FeedbackResource(app)
            elif name == 'notifications':
                return NotificationResource(app)
            elif name == 'disconnections':
                return DisconnectionLogResource(app)
            else:
                return ErrorResource(
                    404, 'Unknown resource', app=self.app_name, 
                    environment=self.environment
                )

    def render_GET(self, request):
        try:
            app = AppRegistry.get(self.app_name, self.environment)
        except NoSuchAppException:
            return ErrorResource(
                404, 'No app registered under that name and environment',
                name=self.app_name,
                environment=self.environment
            ).render(request)
        else:
            return json_response(app.to_simple(), request)

    def render_POST(self, request):
        j = json.loads(request.content.read())
        if 'certificate' not in j:
            return ErrorResource(
                400, '`certificate` is a required key. It must be either a '
                     'path to a .pem file or the contents of the pem itself'
            ).render(request)

        kwargs = {}
        if 'timeout' in j:
            kwargs['timeout'] = int(j['timeout'])

        app = AppRegistry.put(self.app_name, self.environment, 
                              j['certificate'], **kwargs)

        return json_response(app.to_simple(), request, 201)


class AppEnvResourceBase(Resource):
    def __init__(self, app):
        self.app = app


class NotificationResource(AppEnvResourceBase):
    isLeaf = True

    def render_POST(self, request):
        notifications = json.loads(request.content.read())
        is_list = isinstance(notifications, list)
        if is_list:
            is_all_dicts = len(notifications) == \
                sum(1 if (isinstance(el, dict)
                          and 'payload' in el 
                          and 'token' in el
                          and 'identifier' in el
                          and 'expiry' in el) 
                    else 0 for el in notifications)
        else:
            is_all_dicts = False

        if not is_list or not is_all_dicts:
            return ErrorResource(
                400, 'Notifications must be a list of dictionaries in the '
                     'proper format: ['
                     '{"payload": {...}, "token": "...", "identifier": '
                     '"...", "expiry": 30}]'
            ).render(request)

        # returns a deferred but we're not making the client wait
        self.app.notify([Notification.from_simple(n) for n in notifications])

        return json_response({}, request, 201)


class DisconnectionLogResource(AppEnvResourceBase):
    isLeaf = True

    def render_GET(self, request):
        response = json_response([d.to_simple() for d in self.app.disconnections],
                             request)
        self.app.disconnections.clear()
        return response


class FeedbackResource(AppEnvResourceBase):
    isLeaf = True

    def render_GET(self, request):
        def on_done(feedbacks):
            request.write(json_response(feedbacks, request))
            request.finish()
        d = self.app.feedback()
        d.addCallback(on_done)
        return NOT_DONE_YET


default_resource = Resource()
default_resource.putChild('apps', AppRootResource())
