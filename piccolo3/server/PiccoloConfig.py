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

__all__ = ['PiccoloConfig']

import os.path
import logging
from configobj import ConfigObj, flatten_errors
from validate import Validator
from pprint import pprint as pretty # To pretty-print output when testing.

# the defaults
defaultCfgStr = """
# This is the Piccolo instrument configuration file.

[channels]
  [[__many__]]
    direction = string
    reverse = boolean(default=False) # Is the polarity of the shutter connection reversed?
    fibreDiameter = integer(default=600) # micrometres

[spectrometers]
  [[__many__]]
    detectorSetTemperature = float(default=-10.0)
    fan = boolean(default=True)
    power_switch = integer(default=-1) # GPIO pin number used for switch
    min_integration_time = float(default=1000.) # minimum integration time in ms
    max_integration_time = float(default=65535000.) # maximum integration time in ms
    [[[calibration]]]
      [[[[__many__]]]]
        wavelengthCalibrationCoefficientsPiccolo = float_list()

[output]
  # overwrite output files when clobber is set to True
  clobber = boolean(default=False)
  # write separate files containing only dark and light spectra when split is
  # set to True
  split = boolean(default=True)
"""

# populate the default  config object which is used as a validator
piccoloDefaults = ConfigObj(defaultCfgStr.split('\n'),list_values=False,_inspec=True)
validator = Validator()

class PiccoloConfig:
    """object managing the piccolo configuration"""

    def __init__(self):
        self._log = logging.getLogger('piccolo.config')
        self._cfg = ConfigObj(configspec=piccoloDefaults)
        self._cfg.validate(validator)

    def readCfg(self,fname):
        """read and parse configuration file"""

        if not os.path.isfile(fname):
            msg = 'no such configuration file {0}'.format(fname)
            self.log.error(msg)
            raise RuntimeError(msg)


        self._cfg.filename = fname
        self._cfg.reload()
        if not self._cfg.validate(validator):
            msg = 'Could not read config file {0}'.format(fname)
            self.log.error(msg)
            raise RuntimeError(msg)

    @property
    def log(self):
        return self._log

    @property
    def cfg(self):
        return self._cfg
                
if __name__ == '__main__':
    import sys

    cfg = PiccoloConfig()

    if len(sys.argv)>1:
        cfg.readCfg(sys.argv[1])

    print(pretty(cfg.cfg.dict()))

    for s in cfg.cfg['calibrations']:
        print (cfg.getCalibration(s))
