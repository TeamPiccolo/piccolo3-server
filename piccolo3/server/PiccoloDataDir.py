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

__all__ = ['PiccoloDataDir']

from .PiccoloComponent import PiccoloBaseComponent, PiccoloNamedComponent, piccoloGET, piccoloPUT
import os, os.path, glob
import subprocess

class PiccoloRunDir(PiccoloNamedComponent):
    NAME = 'run'

    def __init__(self,datadir,run):
        """
        :param datadir: the data directory object
        :param run: the name of the run
        """
        super().__init__(run)
        self.datadir = datadir
        self._pattern = 'b*_s*.pico'
        self._current_batch = -1
        for s in self.get_spectra_list():
            try:
                b = int(s.split('_')[0][1:])
            except:
                pass
            if b> self._current_batch:
                self._current_batch = b

    def full_path(self,name):
        """construct full path given name"""
        return os.path.join(self.datadir.join(self.name),name)
                
    @piccoloPUT(path="spectra")
    def get_spectra(self,sname):
        data = open(self.full_path(sname),'r').read()
        return data
                
    @piccoloGET
    def get_spectra_list(self):
        spectra = []
        for s in glob.glob(self.full_path(self._pattern)):
            spectra.append(os.path.basename(s))
        spectra.sort()
        return spectra
    
    def get_next_batch(self):
        self._current_batch += 1
        return self._current_batch
    
    @piccoloGET
    def get_name(self):
        return self.name

    @piccoloGET
    def get_current_batch(self):
        return self._current_batch
        
class PiccoloDataDir(PiccoloBaseComponent):
    """manage piccolo output data directory"""

    NAME = 'data_dir'
    
    def __init__(self,datadir,device='/dev/sda1',mntpnt='/mnt',mount=False):
        """
        :param datadir: the data directory. If the path is not absolute then either append datadir to the mount point if mount==True or to the current working directory
        :param device: block device that should get mounted if mount==True
        :param mntpnt: the mount point where the device should get mounted
        :param mount: if device should be mounted
        """

        super().__init__()

        self._device = device
        if mntpnt.endswith(os.sep):
            self._mntpnt = mntpnt[:-1]
        else:
            self._mntpnt = mntpnt

        if mount:
            self.set_mount(True)
            self._datadir = os.path.join(self.mntpnt,datadir)
        else:
            if datadir.startswith(os.sep):
                self._datadir = datadir
            else:
                self._datadir = os.path.join(os.getcwd(),datadir)

        self._check_datadir()

        self._current_run = None
        self._runs = {}
        for r in self.get_runs():
            self.add_run(r)
            
        self.set_current_run('spectra')
                
    @property
    def mntpnt(self):
        return self._mntpnt
    @property
    def datadir(self):
        return self._datadir
    @property
    def device(self):
        return self._device

    def add_run(self,run):
        """register a new run"""
        if run not in self._runs:
            self._runs[run] = PiccoloRunDir(self,run)
            self.coapResources.add_resource(['runs',run],self._runs[run].coapResources)
        return self._runs[run]
    
    def _check_datadir(self):
        """check if data directory exists with correct permissions, if not create it"""
        if not os.path.exists(self.datadir):
            self.log.info("creating data directory {}".format(self.datadir))
            os.makedirs(self.datadir)
        if not os.path.isdir(self.datadir):
            raise RuntimeError('{} is not a directory'.format(self.datadir))
        if not os.access(self.datadir,os.W_OK):
            raise RuntimeError('cannot write to {}'.format(self.datadir))

    @piccoloGET
    def get_mount(self):
        """check if device is mounted in specified location

           :return: True if the device is mounted at the correct mount point
                    False if the device is not mounted
                    raises a RuntimeError if the device is mounted at the wrong
                    mount point"""
        with open('/proc/mounts', 'r') as mnt:
            for line in mnt.readlines():
                fields = line.split()
                if fields[0] == self.device:
                    if fields[1] == self.mntpnt:
                        return True
                    raise RuntimeError("device {} mounted in wrong directory {}".format(self.device,fields[1]))
            return False
        raise OSError ("Cannot read /proc/mounts")

    @piccoloPUT
    def set_mount(self,mount):
        """mount/unmount device at mountpoint

        :param mount: to mount device set to True
                      to unmount device set to False
        """

        msg = ''
        if mount:
            if self.get_mount():
                raise Warning("device {} is already mounted".format(self.device))
            else:
                msg = "mounting {} at {}".format(self.device,self.mntpnt)
                self.log.info(msg)
                cmdPipe = subprocess.Popen(['sudo','mount','-o','uid={},gid={}'.format(os.getuid(),os.getgid()),
                                            self.device,self.mntpnt],stderr=subprocess.PIPE)
                if cmdPipe.wait()!=0:
                    raise OSError('mounting {} at {}: {}'.format(self.device,self.mntpnt, cmdPipe.stderr.read()))
                self._check_datadir()
        else:
           if self.get_mount():
                msg = "unmounting {}".format(self.device)
                self.log.info(msg)
                cmdPipe = subprocess.Popen(['sudo','umount',self.device],stderr=subprocess.PIPE)
                if cmdPipe.wait()!=0:
                    raise OSError('unmounting {}: {}'.format(self.device, cmdPipe.stderr.read()))
           else:
                raise Warning("device {} is already unmounted".format(self.device))
        return msg

    @piccoloGET
    def get_datadir(self):
        return self.datadir

    @piccoloPUT(path="all_runs")
    def get_runs(self,alpha=False,reverse=False,nitems=None,page=0):
        """get list of runs
        :param alpha: set to True to sort names alphanumerically, otherwise sort by time stamp
        :param reverse: set to True to reverse order
        :param nitems: set to number of items in resulting list, by default return all items
        :param page: select page when nitems is set

        TODO: add option to select items since particular timestamp
        """
        runs = []
        for p in os.listdir(self.datadir):
            if os.path.isdir(self.join(p)):
                runs.append(p)
        if alpha:
            # sort alpha numerically
            runs.sort(reverse = reverse)
        else:
            # sort by mtime
            runs.sort(key=lambda p: os.path.getmtime(self.join(p)),reverse = reverse)
        if nitems is not None:
            nchunks = len(runs)//nitems+1
            runs = list((runs[i*nitems:(i+1)*nitems] for i in range(nchunks)))
            runs = runs[page]
        return runs

    @piccoloGET(observable=True)
    def get_current_run(self):
        """get the current run"""
        return self._current_run

    @piccoloPUT
    def set_current_run(self,run):
        """set the current run"""
        if run == self._current_run:
            raise Warning('already using run %s'%run)
        r = self.join(run)
        if not os.path.isdir(r):
            self.log.debug('creating directory for run %s'%run)
            os.makedirs(r)
            self.add_run(run)
        self._current_run = run
        return self._current_run
    
    def join(self,p):
        """join path to datadir if path is not absolute

        :param p: path to be joined"""

        if not os.path.isabs(p):
            return os.path.join(self.datadir,p)
        return p


    # implement methods so object can act as a read-only dictionary
    def keys(self):
        return self._runs.keys()
    def __getitem__(self,r):
        return self._runs[r]
    def __len__(self):
        return len(self._runs)
    def __iter__(self):
        for r in self._runs.keys():
            yield r
    def __contains__(self,r):
        return r in self._runs
        
if __name__ == '__main__':
    from piccolo3.common import piccoloLogging
    piccoloLogging(debug=True)


    t = PiccoloDataDir('/dev/shm/ptest')

    if True:
        import asyncio
        import aiocoap.resource as resource
        import aiocoap

        root = resource.Site()
        root.add_resource(*t.coapSite)
        root.add_resource(('.well-known', 'core'),
                          resource.WKCResource(root.get_resources_as_linkheader))
        asyncio.Task(aiocoap.Context.create_server_context(root))

        asyncio.get_event_loop().run_forever()
