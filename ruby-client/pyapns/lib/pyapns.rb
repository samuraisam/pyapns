$:.unshift(File.dirname(__FILE__)) unless
  $:.include?(File.dirname(__FILE__)) || $:.include?(File.expand_path(File.dirname(__FILE__)))

require 'singleton'
require 'xmlrpc/client'


module PYAPNS  
  VERSION = "0.3.0"
  
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
      perform_call :notify, args, :app_id, :tokens, :notifications, &block
    end

    def feedback(*args, &block)
      perform_call :feedback, args, :app_id, &block
    end

    def perform_call(method, splat, *args, &block)
      if !configured?
        raise PYAPNS::NotConfigured.new
      end
      if splat.length == 1 && splat[0].class == Hash
        splat = args.map { |k| splat[0][k] }
      end
      if (splat.find_all { |l| not l.nil? }).length == args.length
        if block_given?
          Thread.new do 
            perform_call2 {
              block.call(@client.call_async(method.to_s, *splat)) 
            }
          end
          nil
        else
          perform_call2 { @client.call(method.to_s, *args) }
        end
      else
        raise PYAPNS::InvalidArguments.new "Invalid args supplied to #{method.to_s}"
      end
    end
    
    def perform_call2(&block)
      begin
        block.call()
      rescue XMLRPC::FaultException => fault
        case fault.faultCode
        when 404
          raise PYAPNS::UnknownAppID.new
        when 401
          raise PYAPNS::InvalidEnvironment.new
        when 500
          raise PYAPNS::ServerTimeout.new
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
  
  class ClientConfiguration
    # This is middleware for a Rack application
    # it enables you to easily use PYAPNS::Client 
    # within the context of a web application
    # simply call
    #     use PYAPNS::ClientConfiguration(:arg => value, ...)
    # to enable the client's use in your web app
    
    def initialize(app, hash={})
      @app = app
      PYAPNS::Client.configure(hash)
    end
    
    def call(env)
      @app.call(env)
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