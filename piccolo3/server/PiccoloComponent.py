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

__all__ = ['PiccoloBaseComponent','PiccoloNamedComponent']

class PiccoloBaseComponent:
    """
    base class for all components of the piccolo server
    """

    LOGBASE = 'component'

    def __init__(self):
        self._log = logging.getLogger('piccolo.{0}'.format(self.LOGBASE))
        self.log.debug("initialised")

    @property
    def log(self):
        """get the logger"""
        return self._log

class PiccoloNamedComponent(PiccoloBaseComponent):
    """
    a component with a name
    """

    LOGBASE = 'named_component'

    def __init__(self,name):
        """
        :param name: name of the component
        """

        self._name = name
        self._log = logging.getLogger('piccolo.{0}.{1}'.format(self.LOGBASE,name))
        self.log.debug("initialised")

    @property
    def name(self):
        """the name of the component"""
        return self._name

if __name__ == '__main__':
    from piccoloLogging import *
    piccoloLogging(debug=True)
    pc = PiccoloBaseComponent()
    pc.log.info('hello')
    pnc = PiccoloNamedComponent('test')
    pnc.log.info('hello')
