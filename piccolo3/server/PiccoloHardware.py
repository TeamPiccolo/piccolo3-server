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

__all__ = ['piccoloStatusLED','piccoloShutters']

import gpiozero
import time

piccoloStatusLED = gpiozero.LED(25)

class Shutter:

    # The pulse duration required for switching is specified at 5 ms.
    SWITCHING_PULSE_DURATION = 5 # milliseconds 

    def __init__(self,opin,cpin):
        self._open = gpiozero.DigitalOutputDevice(opin)
        self._close = gpiozero.DigitalOutputDevice(cpin)

        self._isOpen = None
        # Close the shutter, to put it into a known state.
        self.close()
        
    @property
    def isOpen(self):
        if self._isOpen is None:
            raise RuntimeError('shutter is in unknown state')
        return self._isOpen
    @property
    def isClosed(self):
        return not self.isOpen
        
    def open(self):
        self._open.on()
        time.sleep(self.SWITCHING_PULSE_DURATION/1000.)
        self._open.off()
        self._isOpen = True

    def close(self):
        self._close.on()
        time.sleep(self.SWITCHING_PULSE_DURATION/1000.)
        self._close.off()
        self._isOpen = False

piccoloShutters = [
    Shutter(17,18),
    Shutter(27,22),
    Shutter(23,24),
]    
