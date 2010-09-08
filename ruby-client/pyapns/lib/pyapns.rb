$:.unshift(File.dirname(__FILE__)) unless
  $:.include?(File.dirname(__FILE__)) || $:.include?(File.expand_path(File.dirname(__FILE__)))

require 'singleton'
require 'xmlrpc/client'

XMLRPC::Config.module_eval {
  remove_const(:ENABLE_NIL_PARSER)  # so that we're not warned about reassigning to a constant
  ENABLE_NIL_PARSER = true          # so that we don't get "RuntimeError: wrong/unknown XML-RPC type 'nil'"
}

module PYAPNS  
  VERSION = "0.3.0"
  
  ## PYAPNS::Client
  ## There's python in my ruby!
  ##
  ## This is a class used to send notifications, provision applications and
  ## retrieve feedback using the Apple Push Notification Service.
  ##
  ## PYAPNS is a multi-application APS provider, meaning it is possible to send
  ## notifications to any number of different applications from the same application
  ## and same server. It is also possible to scale the client to any number
  ## of processes and servers, simply balanced behind a simple web proxy.
  ## 
  ## It may seem like overkill for such a bare interface - after all, the 
  ## APS service is rather simplistic. However, PYAPNS takes no shortcuts when it
  ## comes to compleatness/compliance with the APNS protocol and allows the
  ## user many optimization and scaling vectors not possible with other libraries.
  ## No bandwidth is wasted, connections are persistent and the server is
  ## asynchronous therefore notifications are delivered immediately.
  ##
  ## PYAPNS takes after the design of 3rd party push notification service that
  ## charge a fee each time you push a notification, and charge extra for so-called
  ## 'premium' service which supposedly gives you quicker access to the APS servers.
  ## However, PYAPNS is free, as in beer and offers more scaling oportunites without
  ## the financial draw.
  ##
  ## Provisioning
  ## 
  ## To add your app to the PYAPNS server, it must be `provisioned` at least once.
  ## Normally this is done once upon the start-up of your application, be it a web
  ## service, desktop application or whatever... It must be done at least once
  ## to the server you're connecting to. Multiple instances of PYAPNS will have
  ## to have their applications provisioned individually. To provision an application
  ## manually use the PYAPNS::Client#provision method.
  ## 
  ##    require 'pyapns'
  ##    client = PYAPNS::Client.configure
  ##    client.provision :app_id => 'cf', :cert => '/home/ss/cert.pem', :env => 'sandbox', :timeout => 15
  ##
  ## This basically says "add an app reference named 'cf' to the server and start
  ## a connection using the certification, and if it can't within 15 seconds, 
  ## raise a PYAPNS::TimeoutException
  ##
  ## That's all it takes to get started. Of course, this can be done automatically
  ## by using PYAPNS::ClientConfiguration middleware. PYAPNS::Client is a singleton
  ## class that is configured using the class method PYAPNS::Client#configure. It
  ## is sensibly configured by default, but can be customized by specifying a hash
  ## See the docs on PYAPNS::ClientConfiguration for a list of available configuration
  ## parameters (some of these are important, and you can specify initial applications)
  ## to be configured by default.
  ##
  ## Sending Notifications
  ## 
  ## Once your client is configured, and application provisioned (again, these
  ## should be taken care of before you write notification code) you can begin
  ## sending notifications to users. If you're wondering how to acquire a notification
  ## token, you've come to the wrong place... I recommend using google. However,
  ## if you want to send hundreds of millions of notifications to users, here's how
  ## it's done, one at a time...
  ##
  ## The PYAPNS::Client#notify is a sort of polymorphic method which can notify
  ## any number of devices at a time. It's basic form is as follows:
  ## 
  ##     client.notify 'cf', 'long ass app token', {:aps=> {:alert => 'hello?'}}
  ## 
  ## However, as stated before, it is sort of polymorphic:
  ##
  ##     client.notify 'cf', ['token', 'token2', 'token3'], [alert, alert2, alert3]
  ##     
  ##     client.notify :app_id => 'cf', :tokens => 'mah token', :notifications => alertHash
  ##
  ##     client.notify 'cf', 'token', PYAPNS::Notification('hello tits!')
  ##
  ## As you can see, the method accepts paralell arrays of tokens and notifications
  ## meaning any number of notifications can be sent at once. Hashes will be automatically
  ## converted to PYAPNS::Notification objects so they can be optimized for the wire
  ## (nil values removed, etc...), and you can pass PYAPNS::Notification objects
  ## directly if you wish.
  ## 
  ## Retrieving Feedback
  ##
  ## The APS service offers a feedback functionality that allows application servers
  ## to retrieve a list of device tokens it deems to be no longer in use, and the
  ## time it thinks they stopped being useful (the user uninstalled your app, better
  ## luck next time...) Sounds pretty straight forward, and it is. Apple recommends
  ## you do this at least once an hour. PYAPNS will return an Array of 2-element 
  ## Arrays with the date and the token:
  ##
  ##      feedbacks = client.feedback 'cf'
  ##      => [[#<XMLRPC::DateTime:0x123 ... >, 'token'], 
  ##          [#<XMLRPC::DateTime:0x456 ... >, 'token'], ... ]
  ##
  ## Note that the date is an instance of XMLRPC::DateTime, which you'll probably 
  ## want to call #to_time on to get back a regular Time instance. And, if you're
  ## searching for or comparing the token received, note that it's _lowercase_ hex.
  ##
  ## Asynchronous Calls
  ##
  ## PYAPNS::Client will, by default, perform no funny stuff and operate entirely
  ## within the calling thread. This means that certain applications may hang when,
  ## say, sending a notification, if only for a fraction of a second. Obviously 
  ## not a desirable trait, all `provision`, `feedback` and `notify`
  ## methods also take a block, which indicates to the method you want to call
  ## PYAPNS asynchronously, and it will be done so handily in another thread, calling
  ## back your block with a single argument when finished. Note that `notify` and `provision`
  ## return absolutely nothing (nil, for you rub--wait you are ruby developers!).
  ## It is probably wise to always use this form of operation so your calling thread
  ## is never blocked (especially important in UI-driven apps and asynchronous servers)
  ## Just pass a block to provision/notify/feedback like so:
  ##
  ##     PYAPNS::Client.instance.feedback do |feedbacks|
  ##        feedbacks.each { |f| trim_token f }
  ##     end
  ##
  class Client
    include Singleton

    def self.configure(hash={})
      y = self.instance
      y.configure(hash)
    end

    def initialize
      @configured = false
    end

    def provision(*args, &block)
      perform_call :provision, args, :app_id, :cert, :env, :timeout, &block
    end

    def notify(*args, &block)
      kwargs = [:app_id, :tokens, :notifications]
      get_args(args, *kwargs) do |splat|
        splat[2] = (splat[2].class == Array ? 
                    splat[2] : [splat[2]]).map do |note|
                      if note.class != PYAPNS::Notification
                        PYAPNS::Notification.encode note
                      else
                        note
                      end
                    end
        perform_call :notify, splat, *kwargs, &block
      end
    end

    def feedback(*args, &block)
      perform_call :feedback, args, :app_id, &block
    end

    def perform_call(method, splat, *args, &block)
      if !configured?
        raise PYAPNS::NotConfigured.new
      end
      get_args(splat, *args) do |splat|
        if block_given?
          Thread.new do 
            perform_call2 {
              block.call(@client.call_async(method.to_s, *splat)) 
            }
          end
          nil
        else
          perform_call2 { @client.call_async(method.to_s, *splat) }
        end
      end
    end
    
    def get_args(splat, *args, &block)
      if splat.length == 1 && splat[0].class == Hash
        splat = args.map { |k| splat[0][k] }
      end
      if (splat.find_all { |l| not l.nil? }).length == args.length
        block.call(splat)
      else
        raise PYAPNS::InvalidArguments.new "Invalid args supplied #{args}"
      end
    end

    def perform_call2(&block)
      begin
        block.call()
      rescue XMLRPC::FaultException => fault
        case fault.faultCode
        when 404
          raise PYAPNS::UnknownAppID.new fault.faultString
        when 401
          raise PYAPNS::InvalidEnvironment.new fault.faultString
        when 500
          raise PYAPNS::ServerTimeout.new fault.faultString
        else
          raise fault
        end
      end
    end

    def configured?
      return @configured
    end

    def configure(hash={})
      if configured?
        return self
      end
      h = {}
      hash.each { |k,v| h[k.to_s.downcase] = v }
      @host = h['host'] || "localhost"
      @port = h['port'] || 7077
      @path = h['path'] || '/'
      @timeout = h['timeout'] || 15
      @client = XMLRPC::Client.new3(
        :host => @host, 
        :port => @port, 
        :timeout => @timeout, 
        :path => @path)
      if not h['initial'].nil?
        h['initial'].each do |initial|
          provision(:app_id => initial[:app_id], 
                    :cert => initial[:cert], 
                    :env => initial[:env], 
                    :timeout => initial[:timeout] || 15)
        end
      end
      @configured = true
      self
    end
  end
  
  ## PYAPNS::ClientConfiguration
  ## A middleware class to make PYAPNS::Client easy to use in web contexts
  ##
  ## Automates configuration of the client in Rack environments
  ## using a simple confiuration middleware. To use PYAPNS::Client in
  ## Rack environments with the least code possible use PYAPNS::ClientConfiguration
  ## (no, really, in some cases, that's all you need!) middleware with an optional
  ## hash specifying the client variables. Options are as follows:
  ##
  ##   use PYAPNS::ClientConfiguration(
  ##        :host => 'http://localhost/' 
  ##        :port => 7077,
  ##        :initial => [{
  ##            :app_id => 'myapp',
  ##            :cert => '/home/myuser/apps/myapp/cert.pem',
  ##            :env => 'sandbox',
  ##            :timeout => 15
  ##   }])
  ##
  ## Where the configuration variables are defined:
  ##
  ##    :host     String      the host where the server can be found
  ##    :port     Number      the port to which the client should connect
  ##    :initial  Array       OPTIONAL - an array of INITIAL hashes
  ##
  ##    INITIAL HASHES:
  ##
  ##    :app_id   String      the id used to send messages with this certification
  ##                          can be a totally arbitrary value
  ##    :cert     String      a path to the certification or the certification file
  ##                          as a string
  ##    :env      String      the environment to connect to apple with, always
  ##                          either 'sandbox' or 'production'
  ##    :timoeut  Number      The timeout for the server to use when connecting
  ##                          to the apple servers
  class ClientConfiguration    
    def initialize(app, hash={})
      @app = app
      PYAPNS::Client.configure(hash)
    end
    
    def call(env)
      @app.call(env)
    end
  end
  
  ## PYAPNS::Notification
  ## An APNS Notification
  ##
  ## You can construct notification objects ahead of time by using this class.
  ## However unnecessary, it allows you to programatically generate a Notification
  ## like so: 
  ##
  ##    note = PYAPNS::Notification.new 'alert text', 9, 'flynn.caf', {:extra => 'guid'}
  ##
  ##    -- or --
  ##    note = PYAPNS::Notification.new 'alert text'
  ##
  ## These can be passed to PYAPNS::Client#notify the same as hashes
  ##
  class Notification
    def initialize(*args)
      kwargs = [:alert, :badge, :sound]
      extra = nil
      if args.length == 1 && args[0].class == Hash
        args = kwargs.map { |k| args[0][k] }
      end
      @note = {
        :aps => {
          :alert => args[0].nil? ? nil : args[0].to_s,
          :badge => args[1].nil? ? nil : args[1].to_i,
          :sound => args[2].nil? ? nil : args[2].to_s
        }
      }
      if args.length == 4
        @note = @note.merge(args[3] || {})
      end
    end
    
    def self.aps_attr(*symbols)
      symbols.each do |sy|
        define_method sy do
          instance_variable_get(:@note)[:aps][sy]
        end
        define_method "#{sy}=".to_sym do |val|
          instance_variable_get(:@note)[:aps][sy] = val
        end
      end
    end
    
    aps_attr :alert, :badge, :sound
    
    def extra key
      @note[key]
    end
    
    def set_extra key, val
      @note[key] = val
    end
    
    def encode
      PYAPNS::Notification.encode(@note)
    end
    
    def self.encode note
      ret = {}
      if !note[:aps].nil?
        ret['aps'] = {}
        note[:aps].each do |k, v|
          if !v.nil?
            ret['aps'][k.to_s] = v
          end
        end
      end
      note.keys.find_all { |k| !note[k].nil? && k != :aps }.each do |k|
        ret[k.to_s] = note[k]
      end
      ret
    end
  end
  
  class UnknownAppID < Exception
  end
  
  class NotConfigured < Exception
  end
  
  class InvalidEnvironment < Exception
  end
  
  class ServerTimeout < Exception
  end
  
  class InvalidArguments < Exception
  end
end