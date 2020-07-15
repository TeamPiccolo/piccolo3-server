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

__all__ = ['PiccoloControl']

import asyncio
import janus
from piccolo3.common import PiccoloSpectraList
from .PiccoloComponent import PiccoloBaseComponent, piccoloGET, piccoloPUT, piccoloChanged
from .PiccoloWorkerThreads import PiccoloThread,PiccoloWorkerThread
from .PiccoloDataDir import PiccoloDataDir
from .PiccoloShutter import PiccoloShutters
from .PiccoloSpectrometer import PiccoloSpectrometers
from .PiccoloScheduler import PiccoloScheduler

from queue import Queue
import threading
import logging
import time

class PiccoloOutput(PiccoloThread):
    """piccolo writer thread"""

    def __init__(self,datadir,spectra,daemon=True):

        super().__init__('piccolo_output',daemon=daemon)

        self.datadir = datadir
        self.spectra = spectra

    def run(self):
        while True:
            task = self.spectra.get()
            if task is None:
                self.log.info('stopped output thread')
                return

            spectra = task
            self.log.info('writing spectra {}'.format(spectra.outName))
            try:
                spectra.write(prefix=self.datadir.datadir)
            except Exception as e:
                self.log.error(str(e))

        
class PiccoloControlWorker(PiccoloWorkerThread):
    """piccolo worker thread controlling shutters and spectrometers"""

    def __init__(self,datadir,shutters,spectrometers,busy,paused,tasks,results,info,daemon=True):

        super().__init__('piccolo_worker',busy, tasks, results,info,daemon=daemon)

        self.paused = paused
        self.datadir = datadir
        self.shutters = shutters
        self.spectrometers = spectrometers

        self.spectra = Queue()
        self.outputThread = PiccoloOutput(self.datadir,self.spectra)
        self.outputThread.start()
        
    def update_status(self,status):
        self.info.put(('status',status))
    def update_sequence_number(self,s):
        self.info.put(('sequence',s))

    def stop(self):
        self.spectra.put(None)
        
    def get_task(self,block=True, timeout=None):
        task = super().get_task(block=block, timeout=timeout)

        if task == 'abort':
            if self.busy.locked():
                self.log.info('aborted acquisition')
                return 'abort'
            else:
                self.log.warn('abort called but not busy')
                return
        elif task == 'pause':
            if self.paused.locked():
                # unpause acquisition
                self.log.info('unpause acquisition')
                self.paused.release()
                return 'unpause'
            else:
                # pause acquisition
                self.log.info('pause acquisition')
                self.paused.acquire()
                self.update_status('paused')
                # wait for a new command
                while True:
                    cmd = self.get_task()
                    if cmd in ['shutdown','abort']:
                        self.paused.release()
                        return cmd
                    elif cmd == 'unpause':
                        return
                    else:
                        self.log.warn('acquisition paused')
        else:
            return task

    def process_task(self,task):
        if task is None:
            return
        elif task[0] == 'record':
            self.results.put('ok')
            self.record_sequence(*task[1])
            self.update_status('idle')
        elif task[0] == 'dark':
            self.results.put('ok')
            self.record_dark(task[1])
            self.update_status('idle')
        elif task[0] == 'auto':
            self.results.put('ok')
            self.autointegrate(task[1])
            self.update_status('idle')

    def autointegrate(self,target):
        self.log.debug('autointegrate target={}'.format(target))
        for shutter in self.shutters:
            self.shutters[shutter].closeShutter()
        for shutter in self.shutters:
            self.update_status('autointegrate {}'.format(shutter))
            self.shutters[shutter].openShutter()

            # start autointegration
            for spec in self.spectrometers:
                try:
                    self.spectrometers[spec].autointegrate(shutter,target=target)
                except Exception as e:
                    self.log.warning(str(e))
            time.sleep(0.1)

            # wait for autointegration
            for spec in self.spectrometers:
                while self.spectrometers[spec].status == 'auto':
                    time.sleep(0.1)
                    
            self.shutters[shutter].closeShutter()
                    
    def record(self,channel,dark=False):
        self.log.debug('recording {} dark={}'.format(channel,dark))
        status = channel + ' '
        if dark:
            status += 'dark'
        else:
            status += 'light'
        self.update_status(status)
        for shutter in self.shutters:
            if not dark and shutter == channel:
                self.shutters[shutter].openShutter()
            else:
                self.shutters[shutter].closeShutter()

        # start acquisition
        for spec in self.spectrometers:
            try:
                self.spectrometers[spec].start_acquisition(channel,dark=dark)
            except Exception as e:
                self.log.warning(str(e))

        time.sleep(0.1)
            
        # collect spectra
        spectra = []
        for spec in self.spectrometers:
            try:
                s = self.spectrometers[spec].get_spectrum()
            except Exception as e:
                self.log.warning(str(e))
                continue
            if s is not None:
                spectra.append(s)

        self.shutters[channel].closeShutter()
        return spectra

    def record_dark(self,run_name,batch=None,sequence=0):
        run = self.datadir[run_name]
        if batch is None:
            batch = run.get_next_batch()
        self.log.info("record dark sequence {} of run {} batch {}".format(sequence,batch,run.name))
        spectra = PiccoloSpectraList(run=run_name,batch=batch,seqNr=sequence)
        for shutter in self.shutters:
            for s in self.record(shutter,dark=True):
                spectra.append(s)
        self.spectra.put(spectra)
    
    def record_sequence(self,run_name,nsequence,auto,delay,target):
        run = self.datadir[run_name]
        batch = run.get_next_batch()
        self.log.info("start recording batch {} of run {} with {} sequences".format(batch,run.name,nsequence))

        self.update_sequence_number(-1)

        if auto==0:
            self.autointegrate(target)
            task = self.get_task(block=False)
            if task in ['abort','shutdown']:
                return

        if auto<1:
            # record dark
            self.record_dark(run_name,batch=batch)
            
        for sequence in range(nsequence):
            if auto>0 and sequence%auto == 0:
                self.autointegrate(target)
                task = self.get_task(block=False)
                if task in ['abort','shutdown']:
                    return
                self.record_dark(run_name,batch=batch,sequence=sequence)
                task = self.get_task(block=False)
                if task in ['abort','shutdown']:
                    return
            
            task = self.get_task(block=False)
            if task in ['abort','shutdown']:
                return
            self.log.info("recording sequence {} of run {} batch {}".format(sequence,run.name,batch))
            self.update_sequence_number(sequence)
            spectra = PiccoloSpectraList(run=run_name,batch=batch,seqNr=sequence)
            for shutter in self.shutters:
                for s in self.record(shutter):
                    try:
                        spectra.append(s)
                    except:
                        print (type(s))
                        raise
            self.spectra.put(spectra)
            task = self.get_task(block=False)
            if task in ['abort','shutdown']:
                return
            self.update_status('waiting')
            time.sleep(delay)

        if nsequence>1:
            # record dark
            self.record_dark(run_name,batch=batch,sequence=nsequence-1)
            
class PiccoloControl(PiccoloBaseComponent):
    """the piccolo server"""
    
    NAME = "control"

    def __init__(self,datadir,shutters,spectrometers):
        """
        :param datadir: data directory
        :type datadir: PiccoloDataDir
        :param shutters: the shutters
        :type shutters: PiccoloShutters
        :param spectrometers: the spectrometers
        :type spectrometers: PiccoloSpectrometers
        """
        super().__init__()

        # the various queues
        # The lock prevents two threads using the spectrometer at the same time.
        self._busy = threading.Lock()
        self._paused = threading.Lock()
        loop = asyncio.get_event_loop()
        self._tQ = janus.Queue(loop=loop) # Task queue.
        self._rQ = janus.Queue(loop=loop) # Results queue.
        self._iQ = janus.Queue(loop=loop) # info queue
        
        self._datadir = datadir
        self._shutters = shutters
        self._spectrometers = spectrometers

        self._current_sequence = -1
        self._status = ''
        self._statusChanged = None

        self._numSequences = 1
        self._numSequencesChanged = None
        self._autointegration = -1
        self._autointegrationChanged = None
        self._delay = 0.
        self._delayChanged = None
        
        self._target = 80.
        self._targetChanged = None
        
        # the scheduler for running tasks
        self._scheduler = PiccoloScheduler(db='sqlite:///%s'%self._datadir.join('scheduler.sqlite'))
        self.coapResources.add_resource(['scheduler'],self._scheduler.coapResources)
        
        
        # start the info updater thread        
        self._uiTask = loop.create_task(self._update_info())
        self._schedulerTask = loop.create_task(self._check_scheduler())
        
        self._piccolo = PiccoloControlWorker(self._datadir, self._shutters, self._spectrometers,
                                             self._busy, self._paused,
                                             self._tQ.sync_q, self._rQ.sync_q, self._iQ.sync_q)
        self._piccolo.start()

    def stop(self):
        # send poison pill to worker
        self.log.info('shutting down')
        self._tQ.sync_q.put(None)

    async def _check_scheduler(self):
        """check if a scheduled task should be run"""

        while True:
            while self._busy.locked():
                await asyncio.sleep(1)
            for job in self._scheduler.runable_jobs:
                task = job.job
                if not task:
                    continue

                await self._tQ.async_q.put(task)
                result = await self._rQ.async_q.get()
                if result != 'ok':
                    self.log.error('failed to run task {}: {}'.format(job.jid, result))
            await asyncio.sleep(1)
            
    async def _update_info(self):
        """thread that checks if info needs to be updated"""

        while True:
            task = await self._iQ.async_q.get()
            if task is None:
                self.log.debug('stopping info updater thread')
                return
            try:
                s,t = task
            except:
                self.log.warning('unexpected task {}'.format(task))
                continue

            if s == 'sequence':
                self._current_sequence = t
            elif s == 'status':
                self._status = t
                if self._statusChanged is not None:
                    self._statusChanged()
            else:
                self.log.warning('unknown spec {}={}'.format(s,t))

    @piccoloGET
    def get_numSequences(self):
        return self._numSequences
    @piccoloPUT
    def set_numSequences(self,n):
        n = int(n)
        if n<1:
            raise ValueError('number of sequences must be greater than 0')
        if n!=self._numSequences:
            self._numSequences = n
            if self._numSequencesChanged is not None:
                 self._numSequencesChanged()
    @piccoloChanged
    def callback_numSequences(self,cb):
        self._numSequencesChanged = cb

    @piccoloGET
    def get_autointegration(self):
        return self._autointegration
    @piccoloPUT
    def set_autointegration(self,n):
        n = max(int(n),-1)
        if n!=self._autointegration:
            self._autointegration = n
            if self._autointegrationChanged:
                 self._autointegrationChanged()
    @piccoloChanged
    def callback_autointegration(self,cb):
        self._autointegrationChanged = cb
       
    @piccoloGET
    def get_delay(self):
        return self._delay
    @piccoloPUT
    def set_delay(self,d):
        d = float(d)
        if d <0:
            raise ValueError('delay must be >=0')
        if abs(self._delay-d)>1e-5:
            self._delay = d
            if self._delayChanged:
                 self._delayChanged()
    @piccoloChanged
    def callback_delay(self,cb):
        self._delayChanged = cb

    @piccoloGET
    def get_target(self):
        return self._target
    @piccoloPUT
    def set_target(self,t):
        t = float(t)
        if t <10 or t>90:
            raise ValueError('target must be >=10 and <=90')
        if abs(self._target-t)>1e-5:
            self._target = t
            if self._targetChanged:
                 self._targetChanged()
    @piccoloChanged
    def callback_target(self,cb):
        self._targetChanged = cb

        
    @piccoloPUT
    def record_sequence(self,run=None,nsequence=None,auto=None,delay=None, target=None,at_time=None,interval=None,end_time=None):
        """start recording a batch

        :param run: name of the current run
        :param nsequence: the number of squences to record
        :param auto: can be -1 for never; 0 once at the beginning; otherwise every nth measurement
        :param delay: delay in seconds between each sequence
        :param target: target saturation percentage for autointegration
        :param at_time: the time at which the job should run or None
        :param interval: repeated scheduled run if interval is not set to None
        :param end_time: the time after which the job is no longer scheduled
        """
        
        if nsequence is not None:
            self.set_numSequences(nsequence)
        if auto is not None:
            self.set_autointegration(auto)
        if delay is not None:
            self.set_delay(delay)
        if target is not None:
            self.set_target(target)
        if run is not None:
            try:
                self._datadir.set_current_run(run)
            except Warning:
                pass
            
        job = ('record',(self._datadir.get_current_run(),self.get_numSequences(),self.get_autointegration(),self.get_delay(),self.get_target()))

        if at_time:
            self._scheduler.add(at_time,job,interval=interval,end_time=end_time)
        else:        
            if self._busy.locked():
                raise Warning('piccolo system is busy')
            self._tQ.sync_q.put(job)
            result = self._rQ.sync_q.get()
            if result != 'ok':
                raise RuntimeError(result)
            
    @piccoloPUT
    def auto(self,target=None):
        """determine best integration time

        :param target: target saturation percentage for autointegration
        """
        if self._busy.locked():
            raise Warning('piccolo system is busy')
        if target is not None:
            self.set_target(target)
        self._tQ.sync_q.put(('auto',self.get_target()))
        result = self._rQ.sync_q.get()
        if result != 'ok':
            raise RuntimeError(result)

    @piccoloPUT
    def record_dark(self,run=None):
        """record a dark spectrum

        :param run: name of the current run
        """
        if self._busy.locked():
            raise Warning('piccolo system is busy')
        if run is not None:
            try:
                self._datadir.set_current_run(run)
            except Warning:
                pass
        self._tQ.sync_q.put(('dark',self._datadir.get_current_run()))
        result = self._rQ.sync_q.get()
        if result != 'ok':
            raise RuntimeError(result)             

    @piccoloGET
    def abort(self):
        """abort current batch"""
        if not self._busy.locked():
            raise Warning('piccolo system is not busy')
        self._tQ.sync_q.put('abort')

    @piccoloGET
    def pause(self):
        """pause current batch"""
        if not self._busy.locked():
            raise Warning('piccolo system is not busy')
        self._tQ.sync_q.put('pause')

    @piccoloGET
    def get_current_sequence(self):
        """return current squence number"""
        return self._current_sequence

    @piccoloGET
    def status(self):
        if self._busy.locked():
            return self._status
        else:
            return 'idle'
    @piccoloChanged
    def callback_status(self,cb):
        self._statusChanged = cb
    

    
if __name__ == '__main__':
    from piccolo3.common import piccoloLogging
    piccoloLogging(debug=True)

    
