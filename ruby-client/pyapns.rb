require 'singleton'
require 'xmlrpc/client'

module PYAPNS  
  class Client
    include Singleton
    
    def self.configure(hash={})
      y = self.instance
      y.configure(hash)
    end
    
    def initialize
      @configured = false
    end
  
    def provision(hash={}, &block)
      args = [hash[:app_id], hash[:cert], 
              hash[:environment], hash[:timeout]]
      if (args.find_all { |l| not l.nil? }).length == 4
        perform_call('provision', args, &block)
      else
        raise "Invalid arguments supplied to provision"
      end
    end
  
    def notify(hash={}, &block)
      args = [hash[:app_id], hash[:tokens] || hash[:token], 
              hash[:notifications] || hash[:notification]]PYA
      if (args.find_all { |l| not l.nil? }).length == 3
        perform_call('notify', args, &block)
      else
        raise "Invalid Arguments supplied to notify"
      end
    end
  
    def feedback(hash={}, &block)
      args =[hash[:app_id]]
      if (args.find_all { |l| not l.nil? }).length == 1
        perform_call('feedback', args, &block)
      else
        raise "Invalid arguments supplied to feedback"
      end
    end
    
    def perform_call(method, args, &block)
      if !configured?
        raise "The client is not configured."
      end
      if block
        Thread.new {
          block.call(@client.call_async(method, *args))
        }
      else
        @client.call(method, *args)
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
      return self
    end
  end
end