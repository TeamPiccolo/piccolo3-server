# Copyright 2018 The Piccolo Team
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

__all__ = ["piccoloLogging"]

import logging

def piccoloLogging(logfile = None,debug=False):
    """setup logging

    :param logfile: name of logfile - log to stdout if None
    :param debug: setlog level to debug
    :type debug: logical"""

    log = logging.getLogger("piccolo")

    if debug:
        log.setLevel(logging.DEBUG)
    else:
        log.setLevel(logging.INFO)

    if logfile == None:
        handler = logging.StreamHandler()
    else:
        handler = logging.FileHandler(logfile)

    formatter = logging.Formatter('%(asctime)s %(levelname)s: %(name)s: %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)

    return handler
