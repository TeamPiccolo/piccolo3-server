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

__all__ = ['PiccoloSysinfo']

from .PiccoloComponent import PiccoloBaseComponent, piccoloGET, piccoloPUT
from . import __version__
import psutil
import socket
from datetime import datetime
from pytz import utc
import subprocess

class PiccoloSysinfo(PiccoloBaseComponent):
    """piccolo system information"""
    
    NAME = 'sysinfo'

    @piccoloGET
    def get_cpu(self):
        """get cpu usage (percent)"""
        return psutil.cpu_percent()
    @piccoloGET
    def get_mem(self):
        """get memory usage (percent)"""
        return psutil.virtual_memory().percent
    @piccoloGET
    def get_host(self):
        """get hostname"""
        return socket.gethostname()
    @piccoloGET
    def get_clock(self):
        """get the current date and time"""
        return datetime.now(tz=utc).isoformat()
    @piccoloGET
    def get_version(self):
        """get the server version"""
        return __version__
    @piccoloPUT
    def set_clock(self,clock):
        """set the current date and time

        :param clock: isoformat date and time string used to set the time"""
        self.log.debug('setting system time to \'{}\''.format(clock))
        cmdPipe = subprocess.Popen(['sudo','date','-s',clock],
                                   stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        if cmdPipe.wait()!=0:
            raise OSError('setting time to \'{}\': {}'.format(clock,
                                                              cmdPipe.stderr.read().decode()))

if __name__ == '__main__':
    from piccolo3.common import piccoloLogging
    piccoloLogging(debug=True)

    ps = PiccoloSysinfo()
    
    if True:
        import asyncio
        import aiocoap.resource as resource
        import aiocoap

        root = resource.Site()
        root.add_resource(*ps.coapSite)
        root.add_resource(('.well-known', 'core'),
                          resource.WKCResource(root.get_resources_as_linkheader))
        asyncio.Task(aiocoap.Context.create_server_context(root))

        asyncio.get_event_loop().run_forever()

    else:
        print (ps.get_cpu())
        print (ps.get_mem())
        print (ps.get_host())
        print (ps.get_clock())
    
    
