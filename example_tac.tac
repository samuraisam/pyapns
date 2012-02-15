# CONFIG FILE LOCATION
# relative to this file or absolute path

config_file = 'example_conf.json'

# you don't need to change anything below this line really

import twisted.application, twisted.web, twisted.application.internet
import pyapns.server, pyapns._json
import os

with open(os.path.abspath(config_file)) as f:
    config = pyapns._json.loads(f.read())

application = twisted.application.service.Application("pyapns application")

resource = twisted.web.resource.Resource()
service = pyapns.server.APNSServer()

# get automatic provisioning
if 'autoprovision' in config:
    for app in config['autoprovision']:
        service.xmlrpc_provision(app['app_id'], app['cert'], app['environment'], 
                                 app['timeout'])

# get port from config or 7077
if 'port' in config:
    port = config['port']
else:
    port = 7077

resource.putChild('', service)
site = twisted.web.server.Site(resource)

server = twisted.application.internet.TCPServer(port, site)
server.setServiceParent(application)
