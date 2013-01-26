pyapns
======

A universal Apple Push Notification Service (APNS) provider.

Features:

 * **REST interface** so you can start sending notifications with any language immediately
 * Native Python API included
 * Scalable, fast and easy to distribute behind a proxy
 * Multi-application and dual environment support
 * Disconnection log interface which provides reasons for recent connection issues
 * Supports the full suite of APN gateway functionality

### Quick Start

Install and start the daemon:

    $ sudo easy_install pyapns
    $ wget https://raw.github.com/samuraisam/pyapns/master/pyapns.tac
    $ twistd -ny pyapns.tac 

Provision an app and send a notification:

    $ curl -d '{"certificate":"/path/to/certificate.pem"}'      \
          http://localhost:8088/apps/com.example.app/sandbox

    $ curl -d '{"token": "le_token",                            \
                "payload": {"aps": {"alert": "Hello!"}},        \
                "identifier": "xxx", "expiry": 0}'              \
          http://localhost:8088/apps/com.example.app/sandbox/notifications

### About

pyapns is a daemon that is installed on a server and designed to take the pain out of sending push notifications to Apple devices. Typically your applications you will have a thread that maintains an SSL socket to Apple. This can be error-prone, hard to maintain and plainly a burden your app servers should not have to deal with.

Additionally, pyapns provides several features you just wouldn't get with other solutions such as the disconnection log which remembers which notifications and tokens caused disconnections with Apple - thus allowing your application layer to make decisions about whether or not th continue sending those types of notifications. This also works great as a debugging layer.

pyapns supports sending notifications to multiple applications each with multiple environments. This is handy so you don't have to push around your APN certificates, just keep them all local to your pyapns installation.

## The REST interface

The rest interface is by default hosted on port `8088` and provides all of the functionality you'll need. Here are some basic things you need to know about how it works:

 * All functionality is underneath the `/apps` top level path
 * Functionality specific to individual apps is available underneath the `/apps/{app id}/{environment}` path where `app id` is the provisioned app id and `environment` is the Apple environment (either "sandbox" or "production")
 * You can get a list of provisioned apps: `GET /apps`
 * Objects all have a `type` attribute that tells you which kind of object it is
 * Successful responses will have a top level object with a `response` and `code` keys
 * Unsuccessful responses will have a top level object with an `error` and `code` keys

### Provisioning An App

Before sending notifications to devices, you must first upload your certificate file to the server so pyapns can successfully make a connection to the APN gateway. The certificates must be a PEM encoded file. [This](http://stackoverflow.com/questions/1762555/creating-pem-file-for-apns) stackoverflow answer contains an easy way to accomplish that.

You can upload the PEM and provision the app multiple ways:

 1. Send the PEM file directly when provisioning the apps. Just read the whole PEM file into memory and include it as the `certificate` key:
         ```sh
         $ curl -d '{"certificate": "$(cat /path/to/cert.pem)"}' $HOST:$PORT/apps/com.example.myid/production
         ```
 2. Upload the PEM file ahead of time to the same server as the pyapns daemon and provide the path to the certificate as the `certificate` key:
         ```sh
         $ curl -d '{"certificate": "/path/to/cert.pem"}' $HOST:$PORT/apps/com.example.myid/production
         ```

Notice above that we are including in the URL the app id desired as well as the environment desired. They are the last and 2nd-to-last elements of the path, respectively. So for this url the app id is _com.example.myid_ and the environment is _production_. Any time you access functionality specific to these apps you'll be accessing it as a subpath of this full path.

#### GET _/apps_

Returns a list of all provisioned apps

##### Example Response
```json
{
    "response": [
        {
            "type": "app",
            "certificate": "/path/to/cert.pem",
            "timeout": 15,
            "app_id": "my.app.id",
            "environment": "sandbox"
        }
    ],
    "code": 200
}
```
#### GET _/apps/:app_id/environment_

Returns information about a provisioned app

##### Example Response
```json
{
    "response": {
        "type": "app",
        "certificate": "/path/to/cert.pem",
        "timeout": 15,
        "app_id": "my.app.id",
        "environment": "sandbox"
    },
    "code": 200
}
```

#### POST _/apps/:app_id/:environment_

Creates a newly provisioned app. You can POST multiple times to the same URL and it will merely re-provision the app, taking into account the new certificate and timeout. There may be more config values to provision in the future.

###### Example Body:
```json
{
    "certificate": "certificate or path to certificate",
    "timeout":     15
}
```
##### Example Response
```json
{
    "response": {
        "type": "app",
        "certificate": "/path/to/cert.pem",
        "timeout": 15,
        "app_id": "my.app.id",
        "environment": "sandbox"
    },
    "code": 201
}
```

### Sending Notifications
###### Identifiers and Expiry

#### Retrieving Feedback

#### Retrieving Disconnection Events

### The Included Python API

### Installing in Production

To install in production, you will want a few things that aren't covered in the quickstart above:

 1. Automated provisioning of apps. This is supported when the pyapns server is started up.
 2. Install [python-epoll](http://pypi.python.org/pypi/python-epoll/) and [ujson](http://pypi.python.org/pypi/ujson) for dramatically improved performance
 3. (optional) start multiple instances behind a reverse proxy like HAProxy or Nginx

#### Automated provisioning

#### Production dependencies

#### Example `supervisord` config

#### Multiple instances behind a reverse proxy

