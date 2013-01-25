# CONFIG FILE LOCATION
# relative to this file or absolute path

config_file = '/path/to/config/pyapns_conf.json'

# you don't need to change anything below this line really

import twisted.application, twisted.web, twisted.application.internet
import pyapns.server, pyapns._json
import pyapns.rest_service, pyapns.model
import os

config = {}

if os.path.exists(os.path.abspath(config_file)):
    with open(os.path.abspath(config_file)) as f:
        config.update(pyapns._json.loads(f.read()))
else:
    print 'No config file loaded. Alter the `config_file` variable at', \
          'the top of this file to set one.'

xml_service = pyapns.server.APNSServer()

# get automatic provisioning
if 'autoprovision' in config:
    for app in config['autoprovision']:
        # for XML-RPC
        xml_service.xmlrpc_provision(app['app_id'], app['cert'], 
                                     app['environment'], app['timeout'])
        # for REST
        pyapns.model.AppRegistry.put(
            app['app_id'], app['environment'], app['cert'], 
            timeout=app['timeout']
        )

application = twisted.application.service.Application("pyapns application")

# XML-RPC server support ------------------------------------------------------

if 'port' in config:
    port = config['port']
else:
    port = 7077

resource = twisted.web.resource.Resource()
resource.putChild('', xml_service)

site = twisted.web.server.Site(resource)

server = twisted.application.internet.TCPServer(port, site)
server.setServiceParent(application)

# rest service support --------------------------------------------------------
if 'rest_port' in config:
    rest_port = config['rest_port']
else:
    rest_port = 8088

site = twisted.web.server.Site(pyapns.rest_service.default_resource)

server = twisted.application.internet.TCPServer(rest_port, site)
server.setServiceParent(application)
