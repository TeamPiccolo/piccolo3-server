# Copyright 2018- The Piccolo Team
#
# This file is part of piccolo3-server.
#
# piccolo3-server is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# piccolo3-server is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with piccolo3-server.  If not, see <http://www.gnu.org/licenses/>.

"""
.. moduleauthor:: Magnus Hagdorn <magnus.hagdorn@ed.ac.uk>

"""

import logging
import aiocoap.resource as resource
import aiocoap
import functools
import json

__all__ = ['PiccoloBaseComponent','PiccoloNamedComponent','piccoloGET', 'piccoloPUT','piccoloChanged']

def _extract_path(f,prefix,path):
    if path is None:
        if f.__name__.startswith(prefix):
            p = f.__name__[len(prefix):]
        else:
            p = f.__name__
    else:
        p = path
    return p
        

def piccoloGET(_func=None,*, path=None, observable=False, has_subs=False, parse_path=False):
    @functools.wraps(_func)
    def decorator_get(func):
        func.GET = (_extract_path(func,'get_',path),{"observable":observable,
                                                     "has_subs":has_subs,
                                                     "parse_path":parse_path})
        return func
    if _func is None:
        return decorator_get
    else:
        return decorator_get(_func)

def piccoloPUT(_func=None,*, path=None, has_subs=False, parse_path=False):
    @functools.wraps(_func)
    def decorator_put(func):
        func.PUT = (_extract_path(func,'set_',path),{"has_subs":has_subs,
                                                     "parse_path":parse_path})
        return func
    if _func is None:
        return decorator_put
    else:
        return decorator_put(_func)

def piccoloChanged(_func=None,*, path=None):
    @functools.wraps(_func)
    def decorator_changed(func):
        func.CHANGED = (_extract_path(func,'callback_',path),{})
        return func
    if _func is None:
        return decorator_changed
    else:
        return decorator_changed(_func)
    
class PiccoloCoAPSite(type):
    """
    metaclass used to automatically create coap resources
    """

    def __new__(cls, name, bases, clsdict):
        sites = {}
        for a in clsdict:
            attrib = clsdict[a]
            for m in ['GET','PUT']:
                if (hasattr(attrib,m)):
                    path,kwargs  = getattr(attrib,m)
                    if kwargs['has_subs']:
                        sites[path+'_site'] = resource.Site()
        for s in sites:
            clsdict[s] = sites[s]
        clsobj = super().__new__(cls, name, bases, clsdict)
        return clsobj
    
    def __call__(cls,*args, **kwargs ):
        x = super().__call__(*args,**kwargs)
        x._resources = {}
        for a in dir(x):
            attrib = getattr(x,a)
            for m in ['GET','PUT','CHANGED']:
                if hasattr(attrib,m):
                    path,kwargs  = getattr(attrib,m)
                    if path not in x._resources:
                        x._resources[path] = {"resource_type":PiccoloResource,
                                              "sub_sites": False}
                    if m in x._resources[path]:
                        raise RuntimeError('CoAP operation %s already defined for path %s'%(m,path))
                    x._resources[path][m] = (a,kwargs)
                    if "has_subs" in kwargs and kwargs["has_subs"]:
                        x._resources[path]["sub_sites"] = True
                    if 'parse_path' in kwargs and kwargs['parse_path']:
                        x._resources[path]["resource_type"] = PiccoloResourcePath
                    if m == 'GET' and kwargs["observable"]:
                        if 'parse_path' in kwargs and kwargs['parse_path']:
                            x._resources[path]["resource_type"] = PiccoloObservalbeResourcePath
                        else:
                            x._resources[path]["resource_type"] = PiccoloObservalbeResource
                    if 'CHANGED' in x._resources[path]:
                        if 'parse_path' in kwargs and kwargs['parse_path']:
                            x._resources[path]["resource_type"] = PiccoloObservalbeResourcePath
                        else:
                            x._resources[path]["resource_type"] = PiccoloObservalbeResource
        for p in x._resources:
            r = x._resources[p]["resource_type"](x,x._resources[p])
            if x._resources[p]["sub_sites"]:
                sub_site = getattr(x,p+'_site')
                sub_site.add_resource([],r)
                setattr(x,p,sub_site)
                x.coapResources.add_resource([p], sub_site)
            else:
                x.coapResources.add_resource([p], r)
            if 'CHANGED' in x._resources[p]:
                cb = getattr(x,x._resources[p]['CHANGED'][0])
                cb(r.notify)
        return x

class PiccoloResource(resource.Resource):
    """
    a CoAP resource
    """
    def __init__(self,component,spec):
        super().__init__()
        self._component = component
        self._spec = spec

        self._get = None
        self._put = None
        if 'GET' in self._spec:
            self._get = getattr(self._component,self._spec['GET'][0])
        if 'PUT' in self._spec:
            self._put = getattr(self._component,self._spec['PUT'][0])
        
    @property
    def log(self):
        return self._component.log

    def notify(self):
        pass
    
    async def render_get(self, request):
        args = request.opt.uri_path
        if self._get is None:
            return aiocoap.Message(code=aiocoap.METHOD_NOT_ALLOWED)
        try:
            msg = 'calling {}'.format(self._get.__name__)
            if len(args)>0:
                msg += ' args={}'.format(args)
            self.log.debug(msg)
            result = self._get(*args)
            result = json.dumps(result)
            self.log.debug('result: %s'%(result))
            code = aiocoap.CONTENT
        except Exception as e:
            result = str(e)
            self.log.error(result)
            code = aiocoap.INTERNAL_SERVER_ERROR
        return aiocoap.Message(code=code,payload=result.encode())

    async def render_put(self, request):
        args = list(request.opt.uri_path)
        if self._put is None:
            return aiocoap.Message(code=aiocoap.METHOD_NOT_ALLOWED)    
        # convert payload to json
        try:
            data = json.loads(request.payload.decode())
        except Exception as e:
            e = str(e)
            self.log.error(e)
            return aiocoap.Message(code=aiocoap.BAD_REQUEST, payload=e.encode())
        # payload can be
        if isinstance(data,list):
            # a list
            if len(data) == 2 and isinstance(data[0],list) and isinstance(data[1],dict):
                args += data[0]
                kwargs = data[1]
            else:
                args += data
                kwargs = {}
        elif isinstance(data,dict):
            # a dictionary
            kwargs = data
        else:
            # or a single value
            args += [data]
            kwargs = {}
        self.log.debug('calling {}, args={}, kwargs={}'.format(self._put.__name__,args,kwargs))
        try:
            result = self._put(*args,**kwargs)
        except Warning as e:
            e = str(e)
            self.log.warning(e)
            return aiocoap.Message(code=aiocoap.BAD_REQUEST, payload=e.encode())
        except Exception as e:
            e = str(e)
            self.log.error(e)
            return aiocoap.Message(code=aiocoap.BAD_REQUEST, payload=e.encode())
        if result is not None:
            result = json.dumps(result)
        else:
            result = ""
        self.log.debug('result: %s'%(result))
        if len(result)>0:
            self.notify()
        return aiocoap.Message(code=aiocoap.CHANGED, payload=result.encode())

class PiccoloObservalbeResource(PiccoloResource,resource.ObservableResource):
    def notify(self):
        self.updated_state()
        
class PiccoloResourcePath(PiccoloResource,resource.PathCapable):
    pass

class PiccoloObservalbeResourcePath(PiccoloObservalbeResource,resource.PathCapable):
    pass

class PiccoloBaseComponent(metaclass=PiccoloCoAPSite):
    """
    base class for all components of the piccolo server
    """

    NAME = 'component'
    
    def __init__(self):
        self._log = logging.getLogger(self.logName)
        self._coapResources = resource.Site()
        self.log.debug("initialised")

    @property
    def logName(self):
        return 'piccolo.{0}'.format(self.NAME)        
        
    @property
    def coapResources(self):
        return self._coapResources

    @property
    def coapSite(self):
        return ((self.NAME,),self.coapResources)
        
    @property
    def log(self):
        """get the logger"""
        return self._log

class PiccoloNamedComponent(PiccoloBaseComponent):
    """
    a component with a name
    """

    NAME = 'named_component'

    def __init__(self,name):
        """
        :param name: name of the component
        """

        self._name = name
        super().__init__()
        
    @property
    def name(self):
        """the name of the component"""
        return self._name

    @property
    def logName(self):
        return 'piccolo.{0}.{1}'.format(self.NAME,self.name)

    @property
    def coapSite(self):
        return ((self.NAME,self.name),self.coapResources)
    
if __name__ == '__main__':
    from piccolo3.common import piccoloLogging
    piccoloLogging(debug=True)
    pc = PiccoloBaseComponent()
    pc.log.info('hello')
    pnc = PiccoloNamedComponent('test')
    pnc.log.info('hello')

