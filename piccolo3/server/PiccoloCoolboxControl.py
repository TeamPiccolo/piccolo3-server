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

__all__ = ['PiccoloCoolboxControl']

import asyncio
from .PiccoloComponent import PiccoloBaseComponent, PiccoloNamedComponent, \
    piccoloGET, piccoloPUT, piccoloChanged
import logging

from random import randint

class PiccoloTemperature(PiccoloNamedComponent):
    """manage temperature control on coolbox"""

    NAME = "coolboxctrl"

    def __init__(self,name,target=10):
        super().__init__(name)

        self._target_temp_changed = None
        self.target_temp = target

        self._current_temp_changed = None
        self._current_temp = None

    @property
    def target_temp(self):
        return self._target_temp
    @target_temp.setter
    def target_temp(self,temp):
        self._target_temp = temp
        # do something to the coolbox

        if self._target_temp_changed is not None:
            self._target_temp_changed()
    @piccoloGET
    def get_target_temp(self):
        return self.target_temp
    @piccoloPUT
    def set_target_temp(self,temp):
        self.target_temp = temp
    @piccoloChanged
    def callback_target_temp(self,cb):
        self._target_temp_changed = cb

    @property
    def current_temp(self):
        return self._current_temp
    @current_temp.setter
    def current_temp(self,temp):
        if temp != self._current_temp:
            self._current_temp = temp
            if self._current_temp_changed is not None:
                self._current_temp_changed()
    @piccoloGET
    def get_current_temp(self):
        return self.current_temp
    @piccoloChanged
    def callback_current_temp(self,cb):
        self._current_temp_changed = cb
        
class PiccoloCoolboxControl(PiccoloBaseComponent):
    """manage temperature control on coolbox"""

    NAME = "coolboxctrl"

    def __init__(self,coolbox_cfg):
        super().__init__()

        self._update_interval = coolbox_cfg['update_interval']
        self._temperature_sensors = {}
        for temp in coolbox_cfg['temperature_sensors']:
            self.temperature_sensors[temp] = PiccoloTemperature(temp,
                                                                target=coolbox_cfg['temperature_sensors'][temp]['target'])

        for temp in self.temperature_sensors:
            self.coapResources.add_resource([temp],self.temperature_sensors[temp].coapResources)

        # start the updater thread
        loop = asyncio.get_event_loop()
        self._uiTask = loop.create_task(self._update())
        self.log.info('started')


    async def _update(self):
        """monitor coolbox"""

        while True:
            # read temperature from coolbox
            for temp in self.temperature_sensors:
                self.temperature_sensors[temp].current_temp = randint(0,abs(self.temperature_sensors[temp].target_temp))
                
            await asyncio.sleep(self._update_interval)
    

    @property
    def temperature_sensors(self):
        return self._temperature_sensors

    @piccoloGET
    def get_temperature_sensors(self):
        temp = list(self.temperature_sensors.keys())
        temp.sort()
        return temp

if __name__ == '__main__':
    from piccolo3.common import piccoloLogging
    import aiocoap.resource as resource
    import aiocoap

    piccoloLogging(debug=True)

    coolbox_cfg = {}
    coolbox_cfg['update_interval'] = 5
    coolbox_cfg['temperature_sensors'] = {'temp1': {'target': 10},
                                          'temp2': {'target': 10}}

    coolbox = PiccoloCoolboxControl(coolbox_cfg)

    def start_worker_loop(loop):
        asyncio.set_event_loop(loop)
        loop.run_forever()
        
    root = resource.Site()
    root.add_resource(*coolbox.coapSite)
    root.add_resource(('.well-known', 'core'),
                      resource.WKCResource(root.get_resources_as_linkheader))
    asyncio.Task(aiocoap.Context.create_server_context(root,loggername='piccolo.coap'))

    asyncio.get_event_loop().run_forever()
