# -*- coding: utf-8 -*-
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

import piccolo3.server as piccolo
import asyncio
import aiocoap.resource as resource
import aiocoap
import logging
import os, sys

def piccolo_server(serverCfg):

    log = logging.getLogger("piccolo.server")

    log.info("piccolo3 server version %s"%piccolo.__version__)

    # creat system info
    psys = piccolo.PiccoloSysinfo()
    # create data directory
    pdata = piccolo.PiccoloDataDir(serverCfg.cfg['datadir']['datadir'],
                                   device=serverCfg.cfg['datadir']['device'],
                                   mntpnt=serverCfg.cfg['datadir']['mntpnt'],
                                   mount=serverCfg.cfg['datadir']['mount'])
    # read the piccolo instrument configuration file
    piccoloCfg = piccolo.PiccoloConfig()
    cfgFilename = pdata.join(serverCfg.cfg['config']) # Usually /mnt/piccolo2_data/piccolo.config
    piccoloCfg.readCfg(cfgFilename) 

    # initialise the shutters
    try:
        shutters = piccolo.PiccoloShutters(piccoloCfg.cfg['channels'])
    except:
        log.error('failed to initialise shutters')
        sys.exit(1)

    # initialise the spectrometers
    try:
        spectrometers = piccolo.PiccoloSpectrometers(piccoloCfg.cfg['spectrometers'],shutters.keys())
    except Exception as e:
        log.error('failed to initialise spectrometers', str(e))
        sys.exit(1)

    # initialise the piccolo controller
    controller = piccolo.PiccoloControl(pdata,shutters,spectrometers)

        
    root = resource.Site()
    # add the components
    for c in [psys,pdata,shutters,spectrometers,controller]:
        root.add_resource(*c.coapSite)


    root.add_resource(('.well-known', 'core'),
                      resource.WKCResource(root.get_resources_as_linkheader))
    asyncio.Task(aiocoap.Context.create_server_context(root,
                                                       bind=serverCfg.bind,
                                                       loggername='piccolo.coapserver'))

    asyncio.get_event_loop().run_forever()


    
def main():
    serverCfg = piccolo.PiccoloServerConfig()

    # start logging
    handler = piccolo.piccoloLogging(logfile=serverCfg.cfg['logging']['logfile'],
                                     debug=serverCfg.cfg['logging']['debug'])
    log = logging.getLogger("piccolo.server")

    if serverCfg.cfg['daemon']['daemon']:
        import daemon
        try:
            import lockfile
        except ImportError:
            print ("The 'lockfile' Python module is required to run Piccolo Server. Ensure that version 0.12 or later of lockfile is installed.")
            sys.exit(1)
        try:
            from lockfile.pidlockfile import PIDLockFile
        except ImportError:
            print ("An outdated version of the 'lockfile' Python module is installed. Piccolo Server requires at least version 0.12 or later of lockfile.")
            sys.exit(1)
        from lockfile import AlreadyLocked, NotLocked

        # create a pid file and tidy up if required
        pidfile = PIDLockFile(serverCfg.cfg['daemon']['pid_file'], timeout=-1)
        try:
            pidfile.acquire()
        except AlreadyLocked:
            try:
                os.kill(pidfile.read_pid(), 0)
                print ('Process already running!')
                exit(1)
            except OSError:  #No process with locked PID
                print ('PID file exists but process is dead')
                pidfile.break_lock()
        try:
            pidfile.release()
        except NotLocked:
            pass

        pstd = open(serverCfg.cfg['daemon']['logfile'],'w')
        with daemon.DaemonContext(pidfile=pidfile,
                                  files_preserve = [ handler.stream ],
                                  stderr=pstd):
            # start piccolo
            piccolo_server(serverCfg)
    else:
        # start piccolo
        piccolo_server(serverCfg)

if __name__ == '__main__':
    main()
