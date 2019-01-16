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

__all__ = ['piccoloSysinfoSite']

from PiccoloSysinfo import PiccoloSysinfo

import aiocoap.resource as resource
import aiocoap

class COAPSysinfo(resource.Resource):

    def __init__(self,psysinfo,path):
        super().__init__()
        
        self._piccolo = psysinfo
        self._method = 'get_'+path
        assert hasattr(self._piccolo, self._method)

    def get(self):
        return str(getattr(self._piccolo,self._method)()).encode()

    async def render_get(self, request):
        return aiocoap.Message(payload=self.get())

def piccoloSysinfoSite(psysinfo):
    sysinfo = resource.Site()
    for r in ['cpu','mem','host','clock']:
        sysinfo.add_resource([r],COAPSysinfo(psysinfo,r))
    return sysinfo

if __name__ == '__main__':
    import asyncio
    from piccoloLogging import *
    piccoloLogging(debug=True)

    psysinfo = PiccoloSysinfo()
    
    root = piccoloSysinfoSite(psysinfo)
    root.add_resource(('.well-known', 'core'),
                      resource.WKCResource(root.get_resources_as_linkheader))
    asyncio.Task(aiocoap.Context.create_server_context(root))

    asyncio.get_event_loop().run_forever()
