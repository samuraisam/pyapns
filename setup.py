#!/usr/bin/env python

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

DOC = \
"""
Features:

    * XML-RPC Based, works with any client in any language
    * Native Python API with Django and Pylons support
    * Scalable, fast and easy to distribute behind a proxy
    * Based on Twisted
    * Multi-application and dual environment support
    * Simplified feedback interface

pyapns is an APNS provider that you install on your server and access through XML-RPC.
To install you will need Python, Twisted_ and pyOpenSSL_. It's also recommended to 
install `python-epoll`_ for best performance (if epoll is not available, like on 
Mac OS X, you may want to use another library, like `py-kqueue`_. If you like 
easy_install try (it should take care of the dependancies for you)::

    $ sudo pip install pyapns

pyapns is a service that runs persistently on your machine. To start it::

    $ twistd -r epoll web --class=pyapns.server.APNSServer --port=7077

To get started right away, use the included client::

    $ python
    >>> from pyapns import configure, provision, notify
    >>> configure({'HOST': 'http://localhost:7077/'})
    >>> provision('myapp', open('cert.pem').read(), 'sandbox')
    >>> notify('myapp', 'hexlified_token_str', {'aps':{'alert': 'Hello!'}})

A lot more documentation and the issue tracker can be found on the `github page 
<http://github.com/samuraisam/pyapns>`.
"""

setup(
  name="pyapns",
  version="0.4.0",
  description="A universal Apple Push Notification Service (APNS) provider.",
  long_description=DOC,
  author="Samuel Sutch",
  author_email="samuraiblog@gmail.com",
  license="MIT",
  url="http://github.com/samuraisam/pyapns/tree/master",
  download_url="http://github.com/samuraisam/pyapns/tree/master",
  classifiers = [
    'Development Status :: 4 - Beta',
    'Environment :: Web Environment',
    'Intended Audience :: Developers',
    'License :: OSI Approved :: MIT License',
    'Operating System :: OS Independent',
    'Programming Language :: Python',
    'Topic :: Software Development :: Libraries :: Python Modules'],
  packages=['pyapns'],
  package_data={},
  install_requires=['Twisted>=8.2.0', 'pyOpenSSL>=0.10']
)
