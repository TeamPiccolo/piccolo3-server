# Copyright 2014-2016 The Piccolo Team
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

__all__ = ['PiccoloShutters']

from .PiccoloComponent import PiccoloBaseComponent, PiccoloNamedComponent, piccoloGET, piccoloPUT
import threading
import time

def shutter(shutter,milliseconds):
    """worker function used to open the shutter for the set period

    :param shutter: the shutter instance to operate on
    :type shutter: PiccoloShutter
    :param milliseconds: time to leave shutter open in milliseconds"""
    assert isinstance(shutter,PiccoloShutter)
    
    result = shutter.openShutter()
    if result!='ok':
        return result
    time.sleep(milliseconds/1000.)
    result = shutter.closeShutter()
    return result
    

class PiccoloShutter(PiccoloNamedComponent):
    """class used to control a shutter"""

    NAME = "shutter"
    
    def __init__(self,name,shutter=None,reverse=False,fibreDiameter=600.):
        """
        :param name: name of the component
        :param shutter: the shutter object, if None use dummy
        :param reverse: reverse the polarity of the shutter
        :param fibreDiameter: the diameter of the fibre, used for info
        """

        super().__init__(name)

        self._lock = threading.Lock()
        
        self._fibre = float(fibreDiameter)
        self._reverse = reverse

        self._shutter = shutter
        if self._shutter!=None:
            self.openShutter()
            time.sleep(1)
            self.closeShutter()

    @piccoloGET
    def get_reverse(self):
        """whether polarity is reversed"""
        return self._reverse

    @piccoloGET
    def get_fibre_diameter(self):
        """the diameter of the optical fibre"""
        return self._fibre

    @piccoloPUT
    def set_open_shutter(self,sopen=True):
        """open shutter"""
        if sopen:
            r = self.openShutter()
        else:
            r = self.closeShutter()
        if r != 'ok':
            raise Warning(r)

    @piccoloPUT
    def set_close_shutter(self,sclose=True):
        """close shutter"""
        self.set_open_shutter(not sclose)        
    
    def openShutter(self):
        """open the shutter"""

        if self._lock.locked():
            self.log.warn('shutter already open')
            return 'shutter already open'
        self._lock.acquire()
        self.log.info('open shutter')
        if self._shutter!=None:
            self._shutter.open()
        return 'ok'
        
    def closeShutter(self):
        """close the shutter"""
        
        if not self._lock.locked():
            self.log.info('shutter already closed')
            return 'shutter already closed'
        if self._shutter!=None:
            self._shutter.close()
        self._lock.release()
        self.log.info('closed shutter')
        return 'ok'

    def open_close(self,milliseconds=1000):
        """open the shutter for a set period

        :param milliseconds: time to leave shutter open in milliseconds"""

        self.log.info('opening the shutter for {0} milliseconds'.format(milliseconds))

        t = threading.Thread(target = shutter, args = (self,milliseconds),name=self.name)
        t.daemon=True
        t.start()

    @piccoloGET    
    def status(self):
        """return status of shutter

        :return: *open* if the shutter is open or *closed* if it is closed"""

        if self._lock.locked():
            return 'open'
        else:
            return 'closed'


class PiccoloShutters(PiccoloBaseComponent):
    """manage the shutters"""
    
    NAME = "shutter"

    def __init__(self,shutter_cfg):
        super().__init__()

        self._shutters = {}
        ok = True
        for c in shutter_cfg:
            parsed = c.startswith('shutter_')
            if parsed:
                shutter_num = c.split('_')
                try:
                    shutter_num = int(shutter_num[1])
                except:
                    parsed = False
            if not parsed:
                log.error('cannot parse shutter %s'%c)
                ok = False
                continue

            #TODO: use real shutters
            shutter = None
            
            d = shutter_cfg[c]['direction']
            self.shutters[d] = PiccoloShutter(d, shutter=shutter,
                                              reverse=shutter_cfg[c]['reverse'],
                                              fibreDiameter=shutter_cfg[c]['fibreDiameter'])

        if not ok:
            raise RuntimeError('failed to initialise shutters')

        for s in self.shutters:
            self.coapResources.add_resource([s],self.shutters[s].coapResources)

    @property
    def shutters(self):
        return self._shutters
        
    @piccoloGET#(has_subs=True)
    def get_shutters(self):
        shutters = list(self.shutters.keys())
        shutters.sort()
        return shutters

    # implement methods so object can act as a read-only dictionary
    def keys(self):
        return self.get_shutters()
    def __getitem__(self,s):
        return self.shutters[s]
    def __len__(self):
        return len(self.shutters)
    def __iter__(self):
        for s in self.keys():
            yield s
    def __contains__(self,s):
        return s in self.shutters
        
if __name__ == '__main__':
    from .piccoloLogging import *

    piccoloLogging(debug=True)

    cfg = {"shutter_1": { "direction" : "upwelling",
                          "reverse" : True,
                          "fibreDiameter" : 600},
           "shutter_2": { "direction" : "downwelling",
                          "reverse" : True,
                          "fibreDiameter" : 400}}
    
    s = PiccoloShutters(cfg)

    print (len(s))
    print (s.keys())
    print ('hi' in s, 'downwelling' in s)
    for shutter in s:
        print (shutter,type(s[shutter]))

    if True:
        import asyncio
        import aiocoap.resource as resource
        import aiocoap

        root = resource.Site()
        root.add_resource(*s.coapSite)
        root.add_resource(('.well-known', 'core'),
                          resource.WKCResource(root.get_resources_as_linkheader))
        asyncio.Task(aiocoap.Context.create_server_context(root))

        asyncio.get_event_loop().run_forever()
    else:
        s.openShutter()
        s.openShutter()
        s.closeShutter()
        s.closeShutter()

        s.open_close(5000)
        s.openShutter()

        time.sleep(6)

        s.open_close(5000)
        time.sleep(2)
        s.closeShutter()
        time.sleep(4)
