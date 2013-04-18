try:
    try:
        import ujson # try for ujson first because it rocks and is fast as hell
        class ujsonWrapper(object):
            def dumps(self, obj, *args, **kwargs):
                # ujson dumps method doesn't have separators keyword argument
                if 'separators' in kwargs:
                    del kwargs['separators']
                return ujson.dumps(obj, *args, **kwargs)

            def loads(self, str, *args, **kwargs):
                return ujson.loads(str, *args, **kwargs)
        json = ujsonWrapper()
    except ImportError:
        import json
except (ImportError, NameError):
    try:
        from django.utils import simplejson as json
    except (ImportError, NameError):
        import simplejson as json
try:
    json.dumps
    json.loads
except AttributeError:
    try:  # monkey patching for python-json package
        json.dumps = lambda obj, *args, **kwargs: json.write(obj)
        json.loads = lambda str, *args, **kwargs: json.read(str)
    except AttributeError:
        raise ImportError('Could not load an apropriate JSON library '
                          'currently supported are simplejson, '
                          'python2.6+ json and python-json')

loads = json.loads
dumps = json.dumps
