import twisted.application, twisted.web, twisted.application.internet
import pyapns.server

application = twisted.application.service.Application("pyapns application")

resource = twisted.web.resource.Resource()
resource.putChild('', pyapns.server.APNSServer())
site = twisted.web.server.Site(resource)

server = twisted.application.internet.TCPServer(7077, site)
server.setServiceParent(application)

