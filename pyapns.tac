# CONFIG FILE LOCATION
# relative to this file or absolute path

config_file = '/path/to/config/pyapns_conf.json'

# you don't need to change anything below this line really

import twisted.application, twisted.web, twisted.application.internet
from twisted.python.logfile import LogFile
from twisted.python.log import ILogObserver, FileLogObserver
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

if 'log_file_name' in config:
    log_file_name = config['log_file_name']
else:
    log_file_name = 'twistd.log'

if 'log_file_dir' in config:
    log_file_dir = config['log_file_dir']
else:
    log_file_dir = '.'

if 'log_file_rotate_length' in config:
    log_file_rotate_length = config['log_file_rotate_length']
else:
    log_file_rotate_length = 1000000

if 'log_file_mode' in config:
    log_file_mode = config['log_file_mode']
else:
    log_file_mode = None

if 'log_file_max_rotate' in config:
    log_file_max_rotate = config['log_file_max_rotate']
else:
    log_file_max_rotate = None

application = twisted.application.service.Application("pyapns application")
logfile = LogFile(log_file_name, log_file_dir, log_file_rotate_length, log_file_mode, log_file_max_rotate)
application.setComponent(ILogObserver, FileLogObserver(logfile).emit)

if 'host' in config:
    host = config['host']
else:
    host = ''

# XML-RPC server support ------------------------------------------------------

if 'port' in config:
    port = config['port']
else:
    port = 7077

resource = twisted.web.resource.Resource()
resource.putChild('', xml_service)

site = twisted.web.server.Site(resource)

server = twisted.application.internet.TCPServer(port, site, interface=host)
server.setServiceParent(application)

# rest service support --------------------------------------------------------
if 'rest_port' in config:
    rest_port = config['rest_port']
else:
    rest_port = 8088

site = twisted.web.server.Site(pyapns.rest_service.default_resource)

server = twisted.application.internet.TCPServer(rest_port, site, interface=host)
server.setServiceParent(application)
