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
      get_args args, :app_id, :cert, :env, :timeout do |args|
        perform_call :provision, args, &block
      end
    end

    def notify(*args, &block)
      get_args args, :app_id, :tokens, :notifications do |args|
        perform_call :notify, args, &block
      end
    end

    def feedback(*args, &block)
      get_args args, :app_id do |args|
        perform_call :feedback, args, &block
      end
    end

    def perform_call(method, splat, *args, &block)
      if !configured?
        raise "The client is not configured."
      end
      if block_given?
        Thread.new {
          block.call(@client.call_async(method.to_s, *args))
        }
        nil
      else
        @client.call(method.to_s, *args)
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
                    :environment => initial[:environment], 
                    :timeout => initial[:timeout] || 15)
        end
      end
      @configured = true
      self
    end
    
    def get_args(splat, *args)
      if splat.length == 1 && splat[0].class == Hash
        splat = args.map { |k| splat[0][k] }
      end
      if (splat.find_all { |l| not l.nil? }).length == args.length
        yield splat
      else
        raise "Invalid args supplied"
      end
    end
  end
  
  class ClientConfiguration
    def initialize(app, hash={})
      @app = app
      PYAPNS::Client.configure(hash)
    end
    
    def call(env)
      @app.call(env)
    end
  end
end