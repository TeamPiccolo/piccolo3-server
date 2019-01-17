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

__all__ = ['PiccoloBaseComponent','PiccoloNamedComponent']

class PiccoloCoAPSite(type):
    """
    metaclass used to automatically create coap resources
    """
    def __call__(cls,*args, **kwargs ):
        x = super().__call__(*args,**kwargs)

        for a in dir(x):
            if a.startswith('get_'):
                path = a[4:]
                if 'set_'+path in dir(x):
                    x.coapResources.add_resource([path],PiccoloRWResource(x,path))
                else:
                    x.coapResources.add_resource([path],PiccoloROResource(x,path))

        return x

class PiccoloROResource(resource.Resource):
    """
    a read-only CoAP resource
    """
    def __init__(self,component,path):
        """
        :param component: the piccolo component
        :param path: path to access the resouce
        """

        self._component = component

        self._get_method = 'get_'+path
        assert hasattr(self._component, self._get_method)

    @property
    def log(self):
        return self._component.log
        
    def get(self):
        return str(getattr(self._component,self._get_method)()).encode()

    async def render_get(self, request):
        return aiocoap.Message(payload=self.get())

class PiccoloRWResource(PiccoloROResource):
    """
    a read-write CoAP resource
    """
    def __init__(self,component,path):
        """
        :param component: the piccolo component
        :param path: path to access the resouce
        """

        PiccoloROResource.__init__(self,component,path)

        self._set_method = 'set_'+path
        assert hasattr(self._component, self._set_method)

    def set(self,*args,**kwargs):
        getattr(self._component,self._set_method)(*args,**kwargs)

    async def render_put(self, request):
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
                args = data[0]
                kwargs = data[1]
            else:
                args = data
                kwargs = {}
        elif isinstance(data,dict):
            # a dictionary
            args = []
            kwargs = data
        else:
            # or a single value
            args = [data]
            kwargs = {}
        try:
            self.set(*args,**kwargs)
        except Exception as e:
            e = str(e)
            self.log.error(e)
            return aiocoap.Message(code=aiocoap.BAD_REQUEST, payload=e.encode())
        return aiocoap.Message(code=aiocoap.CHANGED, payload=self.get())
    
class PiccoloBaseComponent(metaclass=PiccoloCoAPSite):
    """
    base class for all components of the piccolo server
    """

    NAME = 'component'
    
    def __init__(self):
        self._log = logging.getLogger('piccolo.{0}'.format(self.NAME))
        self._coapResources = resource.Site()
        self.log.debug("initialised")

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
        self._log = logging.getLogger('piccolo.{0}.{1}'.format(self.NAME,name))
        self.log.debug("initialised")

    @property
    def name(self):
        """the name of the component"""
        return self._name

    @property
    def coapSite(self):
        return ((self.NAME,self.name),self.coapResources)
    
if __name__ == '__main__':
    from piccoloLogging import *
    piccoloLogging(debug=True)
    pc = PiccoloBaseComponent()
    pc.log.info('hello')
    pnc = PiccoloNamedComponent('test')
    pnc.log.info('hello')

