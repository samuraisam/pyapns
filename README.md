pyapns
======

A universal Apple Push Notification Service (APNS) provider.

Features:
<ul>
  <li>XML-RPC Based, works with any client in any language</li>
  <li>Native Python API with Django and Pylons support</li>
  <li>Native Ruby API with Rails/Rack support</li>
  <li>Scalable, fast and easy to distribute behind a proxy</li>
  <li>Based on Twisted</li>
  <li>Multi-application and dual environment support</li>
  <li>Simplified feedback interface</li>
</ul>

pyapns is an APNS provider that you install on your server and access through XML-RPC. To install you will need Python, [Twisted](http://pypi.python.org/pypi/Twisted) and [pyOpenSSL](http://pypi.python.org/pypi/pyOpenSSL). It's also recommended to install [python-epoll](http://pypi.python.org/pypi/python-epoll/) for best performance (if epoll is not available, like on Mac OS X, you may want to use another library, like [py-kqueue](http://pypi.python.org/pypi/py-kqueue/2.0.1)). If you like easy_install try (it should take care of the dependancies for you):

    $ sudo easy_install pyapns
    
pyapns is a service that runs persistently on your machine. To start it:

    $ twistd -r epoll web --class=pyapns.server.APNSServer --port=7077

This will create a `twistd.pid` file in your current directory that can be used to kill the process. `twistd` is a launcher used for running network persistent network applications. It takes many more options that can be found by running `man twistd` or using a [web man page](http://linux.die.net/man/1/twistd).

To get started right away, use the included client:

    $ python
    >>> from pyapns import configure, provision, notify
    >>> configure({'HOST': 'http://localhost:7077/'})
    >>> provision('myapp', open('cert.pem').read(), 'sandbox')
    >>> notify('myapp', 'hexlified_token_str', {'aps':{'alert': 'Hello!'}})

### The Multi-Application Model
pyapns supports multiple applications. Before pyapns can send notifications, you must first provision the application with an Application ID, the environment (either 'sandbox' or 'production') and the certificate file. The `provision` method takes 4 arguments, `app_id`, `path_to_cert_or_cert`, `environment` and `timeout`. A connection is kept alive for each application provisioned for the fastest service possible. The application ID is an arbitrary identifier and is not used in communication with the APNS servers.

When a connection can not be made within the specified `timeout` a timeout error will be thrown by the server. This usually indicates that the wrong [type of] certification file is being used, a blocked port or the wrong environment.

Attempts to provision the same application id multiple times are ignored.

### Sending Notifications
Calling `notify` will send the message immediately if a connection is already established. The first notification may be delayed a second while the server connects. `notify` takes `app_id`, `token_or_token_list` and `notification_or_notification_list`. Multiple notifications can be batched for better performance by using paired arrays of token/notifications. When performing batched notifications, the token and notification arrays must be exactly the same length.

The full notification dictionary must be included as the notification:

    {'aps': {
        'sound': 'flynn.caf',
        'badge': 0,
        'message': 'Hello from pyapns :)'
      }
    } # etc...

### Retrieving Inactive Tokens
Call `feedback` with the `app_id`. A list of tuples will be retrieved from the APNS server that it deems inactive. These are returned as a list of 2-element lists with a `Datetime` object and the token string.

### XML-RPC Methods
These methods can be called on the server you started the server on. Be sure you are not including `/RPC2` in the URL.

### provision

      Arguments
          app_id        String            the application id for the provided
                                          certification
          cert          String            a path to a .pem file or the a
                                          string with the entie file
          environment   String            the APNS server to use - either
                                          'production' or 'sandbox'
          timeout       Integer           timeout for connection attempts to
                                          the APS servers
      Returns
          None

### notify

      Arguments
          app_id        String            the application id to send the
                                          message to
          tokens        String or Array   an Array of tokens or a single
                                          token string
          notifications String or Array   an Array of notification
                                          dictionaries or a single
                                          notification dictionary
      
      Returns
          None

### feedback

      Arguments
          app_id        String            the application id to retrieve
                                          retrieve feedback for
      
      Returns
          Array(Array(Datetime(time_expired), String(token)), ...)
          

### The Python API
pyapns also provides a Python API that makes the use of pyapns even simpler. The Python API must be configured before use but configuration files make it easier. The pyapns `client` module currently supports configuration from Django settings and Pylons config. To configure using Django, the following must be present in  your settings file:

    PYAPNS_CONFIG = {
      'HOST': 'http://localhost:8077/',
      'TIMEOUT': 15,                    # OPTIONAL, host timeout in seconds
      'INITIAL': [                      # OPTIONAL, see below
        ('craigsfish', '/home/samsutch/craigsfish/apscert.pem', 'sandbox'),
      ]
    }

Optionally, with Django settings, you can skip manual provisioning by including a list of `(name, path, environment)` tuples that are guaranteed to be provisioned by the time you call `notify` or `feedback`.

Configuring for pylons is just as simple, but automatic provisioning isn't possible, in your configuration file include:

    pyapns_host = http://localhost:8077/
    pyapns_timeout = 15

For explanations of the configuration variables see the docs for `pyapns.client.configure`.

Each of these functions can be called synchronously and asynchronously. To make them perform asynchronously simply supply a callback. The request will then be made in another thread and your callback will be executed with the results. When calling asynchronously no value will be returned:

    def got_feedback(tuples):
      trim_inactive_tokens(tuples)
    feedback('myapp', callback=got_feedback)

### `pyapns.client.configure(opts)`

    Takes a dictionary of options and configures the client. 
    Currently configurable options are 'HOST', 'TIMEOUT' and 'INITIAL' 
    the latter of which is only read once.
    
    Config Options:
        HOST        - A full host name with port, ending with a forward slash
        TIMEOUT     - An integer specifying how many seconds to timeout a
                      connection to the pyapns server (prevents deadlocking
                      the parent thread).
        INITIAL     - A List of tuples to be supplied to provision when
                      the first configuration happens.

### `pyapns.client.provision(app_id, path_to_cert_or_cert, environment, timeout=15, async=False, callback=None, errback=None)`

    Provisions the app_id and initializes a connection to the APNS server.
    Multiple calls to this function will be ignored by the pyapns daemon
    but are still sent so pick a good place to provision your apps, optimally
    once.
    
    Arguments:
        app_id                 the app_id to provision for APNS
        path_to_cert_or_cert   absolute path to the APNS SSL cert or a 
                               string containing the .pem file
        environment            either 'sandbox' or 'production'
        timeout                number of seconds to timeout connection
                               attempts to the APPLE APS SERVER
        async                  pass something truthy to execute the request in a 
                               background thread
        callback               a function to be executed with the result
        errback                a function to be executed with the error in case of an error

    Returns:
        None

### `pyapns.client.notify(app_id, tokens, notifications, async=False, callback=None, errback=None)`

    Sends push notifications to the APNS server. Multiple 
    notifications can be sent by sending pairing the token/notification
    arguments in lists [token1, token2], [notification1, notification2].
    
    Arguments:
        app_id                 provisioned app_id to send to
        tokens                 token to send the notification or a 
                               list of tokens
        notifications          notification dict or a list of notification dicts
        async                  pass something truthy to execute the request in a 
                               background thread
        callback               a function to be executed with the result when done
        errback                a function to be executed with the error in case of an error

      Returns:
          None

### `pyapns.client.feedback(app_id, async=False, callback=None, errback=None)`

    Retrieves a list of inactive tokens from the APNS server and the times
    it thinks they went inactive.
    
    Arguments:
        app_id                 the app_id to query
        async                  pass something truthy to execute the request in 
                               a background thread
        callback               a function to be executed with the result when 
                               feedbacks are done fetching
        errback                a function to be executed with the error if there
                               is one during the request

    Returns:
        List of feedback tuples like [(datetime_expired, token_str), ...]


## The Ruby API

###PYAPNS::Client
There's python in my ruby!

This is a class used to send notifications, provision applications and
retrieve feedback using the Apple Push Notification Service.

PYAPNS is a multi-application APS provider, meaning it is possible to send
notifications to any number of different applications from the same application
and same server. It is also possible to scale the client to any number
of processes and servers, simply balanced behind a simple web proxy.

It may seem like overkill for such a bare interface - after all, the 
APS service is rather simplistic. However, PYAPNS takes no shortcuts when it
comes to completeness/compliance with the APNS protocol and allows the
user many optimization and scaling vectors not possible with other libraries.
No bandwidth is wasted, connections are persistent and the server is
asynchronous therefore notifications are delivered immediately.

PYAPNS takes after the design of 3rd party push notification service that
charge a fee each time you push a notification, and charge extra for so-called
'premium' service which supposedly gives you quicker access to the APS servers.
However, PYAPNS is free, as in beer and offers more scaling opportunities without
the financial draw.

###Provisioning

To add your app to the PYAPNS server, it must be `provisioned` at least once.
Normally this is done once upon the start-up of your application, be it a web
service, desktop application or whatever... It must be done at least once
to the server you're connecting to. Multiple instances of PYAPNS will have
to have their applications provisioned individually. To provision an application
manually use the `PYAPNS::Client#provision` method.

    require 'pyapns'
    client = PYAPNS::Client.configure
    client.provision :app_id => 'cf', :cert => '/home/ss/cert.pem', :env => 'sandbox', :timeout => 15

This basically says "add an app reference named 'cf' to the server and start
a connection using the certification, and if it can't within 15 seconds, 
raise a `PYAPNS::TimeoutException`

That's all it takes to get started. Of course, this can be done automatically
by using PYAPNS::ClientConfiguration middleware. `PYAPNS::Client` is a singleton
class that is configured using the class method `PYAPNS::Client#configure`. It
is sensibly configured by default, but can be customized by specifying a hash
See the docs on `PYAPNS::ClientConfiguration` for a list of available configuration
parameters (some of these are important, and you can specify initial applications)
to be configured by default.

###Sending Notifications

Once your client is configured, and application provisioned (again, these
should be taken care of before you write notification code) you can begin
sending notifications to users. If you're wondering how to acquire a notification
token, you've come to the wrong place... I recommend using google. However,
if you want to send hundreds of millions of notifications to users, here's how
it's done, one at a time...

The `PYAPNS::Client#notify` is a sort of polymorphic method which can notify
any number of devices at a time. It's basic form is as follows:

    client.notify 'cf', 'long ass app token', {:aps=> {:alert => 'hello?'}}

However, as stated before, it is sort of polymorphic:

    client.notify 'cf', ['token', 'token2', 'token3'], [alert, alert2, alert3]
   
    client.notify :app_id => 'cf', :tokens => 'mah token', :notifications => alertHash

    client.notify 'cf', 'token', PYAPNS::Notification('hello tits!')

As you can see, the method accepts paralell arrays of tokens and notifications
meaning any number of notifications can be sent at once. Hashes will be automatically
converted to `PYAPNS::Notification` objects so they can be optimized for the wire
(nil values removed, etc...), and you can pass `PYAPNS::Notification` objects
directly if you wish.

###Retrieving Feedback

The APS service offers a feedback functionality that allows application servers
to retrieve a list of device tokens it deems to be no longer in use, and the
time it thinks they stopped being useful (the user uninstalled your app, better
luck next time...) Sounds pretty straight forward, and it is. Apple recommends
you do this at least once an hour. PYAPNS will return a list of 2-element lists
with the date and the token:

    feedbacks = client.feedback 'cf'

###Asynchronous Calls

PYAPNS::Client will, by default, perform no funny stuff and operate entirely
within the calling thread. This means that certain applications may hang when,
say, sending a notification, if only for a fraction of a second. Obviously 
not a desirable trait, all `provision`, `feedback` and `notify`
methods also take a block, which indicates to the method you want to call
PYAPNS asynchronously, and it will be done so handily in another thread, calling
back your block with a single argument when finished. Note that `notify` and `provision`
return absolutely nothing (nil, for you rub--wait you are ruby developers!).
It is probably wise to always use this form of operation so your calling thread
is never blocked (especially important in UI-driven apps and asynchronous servers)
Just pass a block to provision/notify/feedback like so:

    PYAPNS::Client.instance.feedback do |feedbacks|
      feedbacks.each { |f| trim_token f }
    end

###PYAPNS::ClientConfiguration
A middleware class to make `PYAPNS::Client` easy to use in web contexts

Automates configuration of the client in Rack environments
using a simple confiuration middleware. To use `PYAPNS::Client` in
Rack environments with the least code possible `use PYAPNS::ClientConfiguration`
(no, really, in some cases, that's all you need!) middleware with an optional
hash specifying the client variables. Options are as follows:

     use PYAPNS::ClientConfiguration(
          :host => 'http://localhost/' 
          :port => 7077,
          :initial => [{
              :app_id => 'myapp',
              :cert => '/home/myuser/apps/myapp/cert.pem',
              :env => 'sandbox',
              :timeout => 15
     }])

Where the configuration variables are defined:

    :host     String      the host where the server can be found
    :port     Number      the port to which the client should connect
    :initial  Array       OPTIONAL - an array of INITIAL hashes

    INITIAL HASHES:

    :app_id   String      the id used to send messages with this certification
                          can be a totally arbitrary value
    :cert     String      a path to the certification or the certification file
                          as a string
    :env      String      the environment to connect to apple with, always
                          either 'sandbox' or 'production'
    :timoeut  Number      The timeout for the server to use when connecting
                          to the apple servers

###PYAPNS::Notification
An APNS Notification

You can construct notification objects ahead of time by using this class.
However unnecessary, it allows you to programmatically generate a Notification
like so: 

    note = PYAPNS::Notification.new 'alert text', 9, 'flynn.caf', {:extra => 'guid'}

    -- or --
    note = PYAPNS::Notification.new 'alert text'

These can be passed to `PYAPNS::Client#notify` the same as hashes

