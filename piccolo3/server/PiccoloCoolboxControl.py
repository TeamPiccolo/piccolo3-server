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
# TODO: Ask Rick where values need to be written to EEPROM

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


class PiccoloSerialConnection(PiccoloBaseComponent):
    """Manage serial connection for controlling and managing the coolbox"""

    def __init__(self, serial_port="/dev/ttyUSB0"):
        super().__init__()
        self.verbose = False
        self.tsleep = 0.001
        self._error_value = 9999.99
        self._serial_port = serial_port
        self.ser = None
        self._serial_lock = asyncio.Lock()
        self.initialize_serial()
        loop = asyncio.get_event_loop()
        task = loop.create_task(self.initialise_coolbox())

    @property
    def error_value(self):
        return self._error_value

    @property
    def serial_port(self):
        return self._serial_port

    @serial_port.setter
    def serial_port(self, serial_port):
        self._serial_port = serial_port
        self.initialize_serial()
        loop = asyncio.get_event_loop()
        task = loop.create_task(self.initialise_coolbox())

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

    async def initialise_coolbox(self):
        async with self._serial_lock:
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

    async def serial_command(self, cmd_str, verbose_message=""):
        async with self._serial_lock:
            try:
                self.ser.open()
                if self.ser.isOpen():
                    self.ser.write(cmd_str.encode())
                    await asyncio.sleep(self.tsleep)
                    serial_data = self.ser.readline()
                    serial_data = self.ser.readline()
                    serial_data = serial_data.decode()
                    serial_data = struct.unpack(
                        '!f', bytes.fromhex(serial_data))[0]
                    if self.verbose:
                        print(verbose_message + " : command string sent was " +
                              cmd_str + " : data recieved back was " + str(serial_data) + "\n")
                    self.ser.close()
                    return data
            except Exception as e:
                self.log.error("Couldn't send serial command " + cmd_str)
                self.log.error(e)
                return self.error_value


class PiccoloTemperature(PiccoloNamedComponent):
    """manage temperature control on coolbox"""

    NAME = "coolboxctrl"

    def __init__(self, name, serial_connection, target=20):
        super().__init__(name)

        self._target_temp_changed = None
        self._target_temp = target

        self._current_temp_changed = None
        self._current_temp = None

        self._serial_connection = serial_connection

    @property
    def serial_connection(self):
        return self._serial_connection

    @property
    def target_temp(self):
        return self._target_temp

    @target_temp.setter
    def target_temp(self, temp):
        self._target_temp = temp
        # do something to the coolbox
        cmd_str = "$R0=" + str(temp) + "\r\n"
        loop = asyncio.get_event_loop()
        task = loop.create_task(self.serial_connection.serial_command(cmd_str))

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

    async def refresh_current_temp(self):
        cmd_str = "$RN100?\r\n"
        current_temp = await self.serial_connection.serial_command(cmd_str)
        self.current_temp = current_temp

    @piccoloGET
    def get_current_temp(self):
        return self.current_temp

    @piccoloChanged
    def callback_current_temp(self, cb):
        self._current_temp_changed = cb


class PiccoloVoltage(PiccoloNamedComponent):
    """Read voltage on coolbox"""

    NAME = "coolboxctrl"

    def __init__(self, name, serial_connection):
        super().__init__(name)

        self._current_voltage = None
        self._current_voltage_changed = None

        self._serial_connection = serial_connection

    @property
    def serial_connection(self):
        return self._serial_connection

    @property
    def current_voltage(self):
        return self._current_voltage

    @current_voltage.setter
    def current_voltage(self, voltage):
        if voltage != self._current_voltage:
            self._current_voltage = voltage
            if self._current_voltage_changed is not None:
                self._current_voltage_changed()

    async def refresh_current_voltage(self):
        cmd_str = "$RN151?\r\n"
        current_voltage = await self.serial_connection.serial_command(cmd_str)
        self.current_voltage = current_voltage

    @piccoloGET
    def get_current_voltage(self):
        return self.current_voltage

    @piccoloChanged
    def callback_current_voltage(self, cb):
        self._current_voltage_changed = cb


class PiccoloCurrent(PiccoloNamedComponent):
    """Read current on coolbox"""

    NAME = "coolboxctrl"

    def __init__(self, name, serial_connection):
        super().__init__(name)

        self._current_current = None
        self._current_current_changed = None

        self._serial_connection = serial_connection

    @property
    def serial_connection(self):
        return self._serial_connection

    @property
    def current_current(self):
        return self._current_current

    @current_current.setter
    def current_current(self, current):
        if current != self._current_current:
            self._current_current = current
            if self._current_current_changed is not None:
                self._current_current_changed()

    async def refresh_current_current(self):
        # TODO may need to make command string a param + put in config to allow for different registers in the serial call. This is currently hard coded to main current.
        cmd_str = "$RN152?\r\n"
        current_current = await self.serial_connection.serial_command(cmd_str)
        self.current_current = current_current

    @piccoloGET
    def get_current_current(self):
        return self.current_current

    @piccoloChanged
    def callback_current_current(self, cb):
        self._current_current_changed = cb


class PiccoloFan(PiccoloNamedComponent):
    """manage fan control on coolbox"""

    NAME = "coolboxctrl"

    def __init__(self, name, serial_connection, fan_state=False):
        super().__init__(name)

        self._target_fan_state_changed = None
        self._target_fan_state = fan_state

        self._current_fan_state_changed = None
        self._current_fan_state = None

        self._serial_connection = serial_connection

    @property
    def serial_connection(self):
        return self._serial_connection

    @property
    def target_fan_state(self):
        return self._target_fan_state

    @target_fan_state.setter
    def target_fan_state(self, fan_state):
        self._target_fan_state = True if fan_state == 1 else False
        # do something to the coolbox
        if self.name == "fan1":
            cmd_str = "$R16="+str(fan_state)+"\r\n"
        else:
            cmd_str = "$R23="+str(fan_state)+"\r\n"
        loop = asyncio.get_event_loop()
        task = loop.create_task(self.serial_connection.serial_command(cmd_str))

        if self._target_fan_state_changed is not None:
            self._target_fan_state_changed()

    @piccoloGET
    def get_target_fan_state(self):
        return self.target_fan_state

    @piccoloPUT
    def set_target_fan_state(self, fan_state):
        self.target_fan_state = fan_state

    @piccoloChanged
    def callback_target_fan_state(self, cb):
        self._target_fan_state_changed = cb

    @property
    def current_fan_state(self):
        return self._current_fan_state

    @current_fan_state.setter
    def current_fan_state(self, fan_state):
        if fan_state != self._current_fan_state:
            self._current_fan_state = fan_state
            if self._current_fan_state_changed is not None:
                self._current_fan_state_changed()

    @piccoloGET
    def get_current_fan_state(self):
        return self.current_fan_state

    @piccoloChanged
    def callback_current_fan_state(self, cb):
        self._current_fan_state_changed = cb


class PiccoloCoolboxControl(PiccoloBaseComponent):
    """manage temperature control on coolbox"""

    NAME = "coolboxctrl"

    def __init__(self, coolbox_cfg):
        super().__init__()
        self._update_interval = coolbox_cfg['update_interval']
        self._serial_connection = PiccoloSerialConnection(
            serial_port=coolbox_cfg['serial_port'])
        self._voltage_sensors = {"voltage": PiccoloVoltage(
            "voltage", serial_connection=self.serial_connection)}
        self._current_sensors = {"current": PiccoloCurrent(
            "current", serial_connection=self.serial_connection)}
        self._fan_sensors = {}
        self._temperature_sensors = {}
        for fan in coolbox_cfg['fans']:
            self.fan_sensors[fan] = PiccoloFan(
                fan, serial_connection=self.serial_connection, fan_state=coolbox_cfg['fans'][fan]['fan_on'])
        for temp in coolbox_cfg['temperature_sensors']:
            self.temperature_sensors[temp] = PiccoloTemperature(
                temp, serial_connection=self.serial_connection, target=coolbox_cfg['temperature_sensors'][temp]['target'])

        for fan in self.fan_sensors:
            self.coapResources.add_resource(
                [fan], self.fan_sensors[fan].coapResources)

        for temp in self.temperature_sensors:
            self.coapResources.add_resource(
                [temp], self.temperature_sensors[temp].coapResources)

        for volts in self.voltage_sensors:
            self.coapResources.add_resource(
                [volts], self.voltage_sensors[volts].coapResources)

        for current in self.current_sensors:
            self.coapResources.add_resource(
                [current], self.current_sensors[current].coapResources)

        # start the updater thread
        loop = asyncio.get_event_loop()
        self._uiTask = loop.create_task(self._update())
        self.log.info('started')

    async def _update(self):
        """monitor coolbox"""

        while True:
            log_string = ""
            for temp in self.temperature_sensors:
                await self.temperature_sensors[temp].refresh_current_temp()
                log_string += "Temperature sensor " + \
                    str(temp) + ": " + \
                    str(self.temperature_sensors[temp].get_current_temp()) + \
                    ", and target temp: " + \
                    str(self.temperature_sensors[temp].get_target_temp())

            for volt in self.voltage_sensors:
                await self.voltage_sensors[volt].refresh_current_voltage()
                log_string += ". Voltage sensor " + \
                    str(volt) + ": " + \
                    str(self.voltage_sensors[volt].get_current_voltage())

            for curr in self.current_sensors:
                await self.current_sensors[curr].refresh_current_current()
                log_string += ". Current sensor " + \
                    str(curr) + ": " + \
                    str(self.current_sensors[curr].get_current_current())

            for fan in self.fan_sensors:
                log_string += ". Fan " + str(curr) + " target state: " + str(
                    self.fan_sensors[fan].target_fan_state) + ", current state: " + str(self.fan_sensors[fan].current_fan_state)

            log_string += ". Serial location: " + \
                str(self.serial_connection.serial_port)

            self.log.info("Coolbox readings: " + log_string)

            await asyncio.sleep(self._update_interval)

    @property
    def serial_connection(self):
        return self._serial_connection

    @property
    def temperature_sensors(self):
        return self._temperature_sensors

    @temperature_sensors.setter
    def temperature_sensors(self, sensor):
        self._temperature_sensors = sensor

    @piccoloGET
    def get_temperature_sensors(self):
        temp = list(self.temperature_sensors.keys())
        temp.sort()
        return temp

    @property
    def fan_sensors(self):
        return self._fan_sensors

    @fan_sensors.setter
    def fan_sensors(self, sensor):
        self._fan_sensors = sensor

    @piccoloGET
    def get_fan_sensors(self):
        fans = list(self.fan_sensors.keys())
        fans.sort()
        return fans

    @property
    def voltage_sensors(self):
        return self._voltage_sensors

    @piccoloGET
    def get_voltage_sensors(self):
        volts = list(self.voltage_sensors.keys())
        volts.sort()
        return volts

    @property
    def current_sensors(self):
        return self._current_sensors

    @piccoloGET
    def get_current_sensors(self):
        current = list(self.current_sensors.keys())
        current.sort()
        return current


if __name__ == '__main__':
    from piccolo3.common import piccoloLogging
    import aiocoap.resource as resource
    import aiocoap

    piccoloLogging(debug=True)

    coolbox_cfg = {}
    coolbox_cfg['update_interval'] = 5

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
