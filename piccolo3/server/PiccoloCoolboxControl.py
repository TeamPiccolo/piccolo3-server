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
import serial
import logging

from random import randint


class PiccoloSerialConnection(PiccoloNamedComponent):
    """Manage serial connection for controlling and managing the coolbox"""

    def __init__(self, serial_port="/dev/ttyUSB0"):
        super().__init__()
        self.verbose = False
        self.tsleep = 0.001
        self._serial_port = serial_port
        self.ser = None
        self.initialize_serial()
        self.initialise_coolbox()

    @property
    def serial_port(self):
        return self._serial_port

    def initialize_serial(self):
        try:
            self.ser = serial.Serial(
                port=self.serial_port,
                timeout=1,
                baudrate=115200,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                bytesize=serial.EIGHTBITS
            )
            self.ser.close()
            if self.verbose:
                print("Coolbox serial connecction initialized.")
            self.log.info("Succesfully initialized coolbox serial connection.")
        except Exception as e:
            self.log.debug("Couldn't open serial connection to the coolbox.")
            self.log.debug("Serial error:", e)

    def initialise_coolbox(self):
        try:
            self.ser.open()
            if self.ser.isOpen():
                # Ensure mode is PID (6) or use 0 for no regulation
                cmd_str = "$R13=6\r\n"
                self.ser.write(cmd_str.encode())
                cmd_str = "$W\r\n"
                self.ser.write(cmd_str.encode())
                cmd_str = "$RW\r\n"
                self.ser.write(cmd_str.encode())
                if self.verbose:
                    print("Coolbox initiallised")
            self.ser.close()
            self.log.info("Successfully initialized coolbox.")
        except Exception as e:
            self.log.error("Couldn't initialize coolbox.")
            self.log.error(e)

    async def check_serial_not_in_use(self):
        for i in range(5):  # Check 5 times before giving up.
            try:
                if self.ser.isOpen():
                    if self.verbose:
                        print("Heater serial port is in use")
                    await asyncio.sleep(self.tsleep)
            except Exception as e:
                if self.verbose:
                    print(
                        "ser.isOpen() failed. Probably couldn't establish a serial connection. Attempt " + str(i) + " of 5")
                if i == 5:
                    self.log.warning("Failed to check serial not in use.")
        try:
            self.ser.close()
        except Exception as e:
            self.log.error(e)

    async def get_serial_data(self, cmd_str, verbose_message):
        self.ser.write(cmd_str.encode())
        await asyncio.sleep(self.tsleep)
        serial_data = self.ser.readline()
        serial_data = self.ser.readline()
        serial_data = serial_data.decode()
        serial_data = struct.unpack('!f', bytes.fromhex(serial_data))[0]
        if self.verbose:
            print(verbose_message + " : command string sent was " +
                  cmd_str + " : data recieved back was " + str(serial_data) + "\n")
        return data


class PiccoloTemperature(PiccoloNamedComponent):
    """manage temperature control on coolbox"""

    NAME = "coolboxctrl"

    def __init__(self, name, target=10):
        super().__init__(name)

        self._target_temp_changed = None
        self.target_temp = target

        self._current_temp_changed = None
        self._current_temp = None

    @property
    def target_temp(self):
        return self._target_temp

    @target_temp.setter
    def target_temp(self, temp):
        self._target_temp = temp
        # do something to the coolbox

        if self._target_temp_changed is not None:
            self._target_temp_changed()

    @piccoloGET
    def get_target_temp(self):
        return self.target_temp

    @piccoloPUT
    def set_target_temp(self, temp):
        self.target_temp = temp

    @piccoloChanged
    def callback_target_temp(self, cb):
        self._target_temp_changed = cb

    @property
    def current_temp(self):
        return self._current_temp

    @current_temp.setter
    def current_temp(self, temp):
        if temp != self._current_temp:
            self._current_temp = temp
            if self._current_temp_changed is not None:
                self._current_temp_changed()

    @piccoloGET
    def get_current_temp(self):
        return self.current_temp

    @piccoloChanged
    def callback_current_temp(self, cb):
        self._current_temp_changed = cb


class PiccoloCoolboxControl(PiccoloBaseComponent):
    """manage temperature control on coolbox"""

    NAME = "coolboxctrl"

    def __init__(self, coolbox_cfg):
        super().__init__()

        self._update_interval = coolbox_cfg['update_interval']
        self._temperature_sensors = {}
        for temp in coolbox_cfg['temperature_sensors']:
            self.temperature_sensors[temp] = PiccoloTemperature(temp,
                                                                target=coolbox_cfg['temperature_sensors'][temp]['target'])

        for temp in self.temperature_sensors:
            self.coapResources.add_resource(
                [temp], self.temperature_sensors[temp].coapResources)

        # start the updater thread
        loop = asyncio.get_event_loop()
        self._uiTask = loop.create_task(self._update())
        self.log.info('started')

    async def _update(self):
        """monitor coolbox"""

        while True:
            # read temperature from coolbox
            for temp in self.temperature_sensors:
                self.temperature_sensors[temp].current_temp = randint(
                    0, abs(self.temperature_sensors[temp].target_temp))

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
    asyncio.Task(aiocoap.Context.create_server_context(
        root, loggername='piccolo.coap'))

    asyncio.get_event_loop().run_forever()
