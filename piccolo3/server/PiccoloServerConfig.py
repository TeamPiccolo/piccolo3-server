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

__all__ = ['PiccoloServerConfig']

from configobj import ConfigObj
from validate import Validator
from argparse import ArgumentParser
import socket
import sys

# the defaults
defaultCfgStr = """
# Piccolo Server Configuration
#
# This configuration file controls the basic operation of the piccolo server.
#

# the piccolo configuration file
# look for config in data directory if the path is relative
config = string(default=piccolo.config)

[logging]
# enable debugging to get extra verbose log
debug = boolean(default=False)
# log to logfile if set otherwise log to stdout
logfile = string(default=None)

[daemon]
# run piccolo server as daemon
daemon = boolean(default=False)
# name of PID file
pid_file = string(default=/var/run/piccolo.pid)
# log daemon messages to logfile, default /var/log/piccolo.err
logfile = string(default=/var/log/piccolo.err)

[datadir]
# control location of output files
# if datadir is a relative path (ie it does not start with a /) write to PWD or
# if requested to the mounted device
datadir = string(default=pdata)
# set to true to mount a block device (eg a USB stick) for writing data
mount = boolean(default=False)
# device to be mounted
device = string(default=/dev/sda1)
# the mount point
mntpnt = string(default=/mnt)

[coap]
# The server address to listen on, can be an IP address or resolvable host name. By default listen on all interfaces
address = string(default="::")
# The port to listen on. By default use the CoAP port 5683
port = integer(default=5683)
"""

# populate the default server config object which is used as a validator
piccoloServerDefaults = ConfigObj(defaultCfgStr.split('\n'))
validator = Validator()

class PiccoloServerConfig(object):
    """object managing the piccolo server configuration"""

    def __init__(self):
        self._cfg = ConfigObj(configspec=piccoloServerDefaults)
        self._cfg.validate(validator)

        parser = ArgumentParser()
        parser.add_argument('-s','--server-configuration',metavar='CFG',help="read configuration from CFG")
        parser.add_argument('-d', '--debug', action='store_true',default=None,help="enable debugging output")
        parser.add_argument('-l', '--log-file',metavar="FILE",help="send piccolo log to FILE, default stdout")

        parser.add_argument('-v','--version',action='store_true',default=False,help="print version and exit")

        daemongroup = parser.add_argument_group('daemon')
        daemongroup.add_argument('-D','--daemonize',default=None,action='store_true',help="start piccolo server as daemon")
        daemongroup.add_argument('-p','--pid-file',default=None,help="name of the PID file")
        daemongroup.add_argument('-L','--daemon-log-file',help="send daemon log to file, default {}".format(self._cfg['daemon']['logfile']))
        
        datagroup = parser.add_argument_group('datadir')
        datagroup.add_argument('-o','--data-dir',help="name of data directory, default {}".format(self._cfg['datadir']['datadir']))
        datagroup.add_argument('-m','--mount',default=None,action='store_true',help="mount a device for writing data")

        args = parser.parse_args()

        if args.version:
            from piccolo3.server import __version__
            print (__version__)
            sys.exit(0)
        
        if args.server_configuration!=None:
            self._cfg.filename = args.server_configuration
            self._cfg.reload()
            self._cfg.validate(validator)
        if args.debug is not None:
            self._cfg['logging']['debug'] = args.debug
        if args.log_file is not None:
            self._cfg['logging']['logfile'] = args.log_file

        if args.daemonize is not None:
            self._cfg['daemon']['daemon'] = args.daemonize
        if args.pid_file is not None:
            self._cfg['daemon']['pid_file'] = args.pid_file
        if args.daemon_log_file is not None:
            self._cfg['daemon']['logfile'] = args.daemon_log_file
            
        if args.data_dir is not None:
            self._cfg['datadir']['datadir'] = args.data_dir
        if args.mount is not None:
            self._cfg['datadir']['mount'] = args.mount

    @property
    def cfg(self):
        return self._cfg

    @property
    def bind(self):
        return socket.getaddrinfo(self.cfg['coap']['address'],self.cfg['coap']['port'],
                                  type=socket.SOCK_DGRAM, family=socket.AF_INET6,
                                  flags=socket.AI_V4MAPPED)[0][-1]

        
if __name__ == '__main__':

    cfg = PiccoloServerConfig()
    print(cfg.cfg)
