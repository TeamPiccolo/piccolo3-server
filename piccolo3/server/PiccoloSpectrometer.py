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

__all__ = ['PiccoloSpectrometers']

from .PiccoloComponent import PiccoloBaseComponent, PiccoloNamedComponent, piccoloGET, piccoloPUT, piccoloChanged
import threading
from queue import Queue
import logging
import uuid
import time


class PiccoloSpectrometerWorker(threading.Thread):
    """Spectrometer worker thread object. The worker thread performs assigned
    tasks in the background and holds on to the results until they are
    picked up."""

    def __init__(self, name, spectrometer, channels, busy, tasks, results,info,daemon=True):
        """Initialize the worker thread.

        Note: calling __init__ does not start the thread, a subsequent call to
        start() is needed to start the thread.

        :param name: a descriptive name for the spectrometer.
        :type name: str
        :param spectrometer: the actual spectrometer object
        :type spectrometer: PiccoloSpectrometer
        :param channels: the list of channels
        :param busy: a "lock" which prevents using the spectrometer when it is busy
        :type busy: thread.lock
        :param tasks: a queue into which tasks will be put
        :type tasks: Queue.Queue
        :param results: the results queue from where results will be collected
        :type results: Queue.Queue
        :param info: queue for reporting back info
        :type info: Queue.Queue
        """
        
        super().__init__()

        self.name = name
        self.daemon = daemon
        
        self._log = logging.getLogger('piccolo.spectrometer_worker.{}'.format(name))
        self.log.info('initialising worker')

        self._busy = busy
        self._tQ = tasks
        self._rQ = results
        self._iQ = info

        # the integration times
        self._currentIntegrationTime = {}
        self._auto = {}
        self._channels = channels
        for c in self.channels:
            self._currentIntegrationTime[c] = None
            self._auto[c] = None
        
        self._maxIntegrationTime = None
        self._minIntegrationTime = None
        

        self.minIntegrationTime = 0
        self.maxIntegrationTime = 10000
        for c in self.channels:
            self.set_currentIntegrationTime(c,1)
            self.set_auto(c,'n')
        
    @property
    def log(self):
        """the worker log"""
        return self._log
    @property
    def busy(self):
        """the busy lock"""
        return self._busy
    @property
    def tasks(self):
        """the task queue"""
        return self._tQ
    @property
    def results(self):
        """the results queue"""
        return self._rQ
    @property
    def info(self):
        """the info queue"""
        return self._iQ
    @property
    def channels(self):
        return self._channels

    
    @property
    def maxIntegrationTime(self):
        return self._maxIntegrationTime
    @maxIntegrationTime.setter
    def maxIntegrationTime(self,t):
        t = int(t)
        if t == self._maxIntegrationTime:
            return
        self._maxIntegrationTime = t
        self.info.put(('max',t))
        for c in self.channels:
            it = self.get_currentIntegrationTime(c) 
            if it is not None and it > self.maxIntegrationTime:
                self.set_currentIntegrationTime(c,self.maxIntegrationTime)
    @property
    def minIntegrationTime(self):
        return self._minIntegrationTime
    @minIntegrationTime.setter
    def minIntegrationTime(self,t):
        t = int(t)
        if t == self._minIntegrationTime:
            return
        self._minIntegrationTime = t
        self.info.put(('min',t))
        for c in self.channels:
            it = self.get_currentIntegrationTime(c) 
            if it is not None and it<self.minIntegrationTime:
                self.set_currentIntegrationTime(c,self.minIntegrationTime)

    def get_currentIntegrationTime(self,c):
        return self._currentIntegrationTime[c]
    def set_currentIntegrationTime(self,c,t,reset_auto = True):
        t = int(t)
        if t == self._currentIntegrationTime[c]:
            return
        if self.minIntegrationTime is not None and t < self.minIntegrationTime:
            raise ValueError("integration time {} is smaller than minimum {}".format(t,self.minIntegrationTime))
        if self.maxIntegrationTime is not None and t>self.maxIntegrationTime:
            raise ValueError("integration time {} is larger than maximum {}".format(t,self.maxIntegrationTime))
        
        self._currentIntegrationTime[c] = t
        self.info.put(('current',(c,t)))
        if reset_auto:
            # reset autointegration state
            self.set_auto(c,'n')

    def get_auto(self,c):
        return self._auto[c]
    def set_auto(self,c,s):
        if s == self.get_auto(c):
            return
        self._auto[c] = s
        self.info.put(('auto',(c,s)))
        
    def run(self):
        while True:
            # wait for a new task from the task queue
            task = self.tasks.get()

            if self.busy.locked():
                self.results.put('spectrometer {} is busy'.format(self.name))
                continue
            self.busy.acquire()
            
            self.log.debug('got task {}'.format(task))
            if task is None:
                # The worker thread can be stopped by putting a None onto the task queue.
                self.info.put(None)
                self.log.info('Stopped worker thread for specrometer {}.'.format(self.name))
                return

            if task[0] == 'current':
                result = 'ok'
                try:
                    self.set_currentIntegrationTime(task[1],task[2])
                except Exception as e:
                    result = str(e)
                self.results.put(result)
            elif task[0] == 'min':
                result = 'ok'
                try:
                    self.minIntegrationTime = task[1]
                except Exception as e:
                    result = str(e)
                self.results.put(result)
            elif task[0] == 'max':
                result = 'ok'
                try:
                    self.maxIntegrationTime = task[1]
                except Exception as e:
                    result = str(e)
                self.results.put(result)
            elif task[0] == 'start_acquisition':
                channel = task[1]
                if channel not in self.channels:
                    self.result.put('channel {} is unknown'.format(channel))
                    continue
                task_id = task[2]
                self.results.put('ok')

                self.log.info("acquisition {}: channel {}, integration time {}".format(str(task_id),channel,self.get_currentIntegrationTime[channel]))
                # create new spectrum instance
                spectrum = {}#PiccoloSpectrum()
                spectrum['name'] = self.name

                # record data

                # If spectrometer is None, thenm simulate a spectrometer, for
                # testing purposes.
                time.sleep(self.currentIntegrationTime/1000.)
                pixels = [1]*100

                #spectrum.pixels = pixels
                spectrum['data'] = 'some data'

                self.info.put(('spectrum',(task_id,spectrum)))
            else:
                result = 'unkown task: {}'.format(task)
                self.results.put(result)

            self.busy.release()
                
class PiccoloSpectrometer(PiccoloNamedComponent):
    """frontend class used to communicate with spectrometer"""

    NAME = 'spectrometer'
    
    def __init__(self,name, channels, spectrometer=None):
        """Initialize a Piccolo Spectrometer object for Piccolo Server.

        The spectromter parameter must be the Spectrometer object from the
        Piccolo Hardware module, such as OceanOpticsUSB2000Plus or
        OceanOpticsQEPro.

        name is a descriptive name for the spectrometer.

        :param name: a descriptive name for the spectrometer.
        :param channels: a list of channels
        :param spectrometer: the spectromtere, which may be None.
        """

        super().__init__(name)

        # the various queues
        # The lock prevents two threads using the spectrometer at the same time.
        self._busy = threading.Lock()
        self._tQ = Queue() # Task queue.
        self._rQ = Queue() # Results queue.
        self._iQ = Queue() # info queue
        
        self._channels = channels
        self._currentIntegrationTime = {}
        self._auto_state = {}
        self._currentIntegrationTimeChanged = None
        self._auto_changed = None
        for c in channels:
            self._currentIntegrationTime[c] = -1
            self._auto_state[c] = None
            
        self._maxIntegrationTime = -1
        self._maxIntegrationTimeChanged = None
        self._minIntegrationTime = -1
        self._minIntegrationTimeChanged = None

        # the spectrum
        self._task_id = None
        self._spectrum = None
        self._have_spectrum = threading.Event()

        # start the info updater thread
        self._uiThread = threading.Thread(target=self._update_info)
        self._uiThread.start()

        # start the spectrometer worker thread
        self._spectrometer = PiccoloSpectrometerWorker(name,spectrometer,
                                                       channels,
                                                       self._busy,
                                                       self._tQ, self._rQ,
                                                       self._iQ)
        self._spectrometer.start()

    def stop(self):
        # send poison pill to worker
        self.log.info('shutting down')
        self._tQ.put(None)
        
    def _update_info(self):
        """thread that checks if info needs to be updated"""

        while True:
            task = self._iQ.get()
            if task is None:
                self.log.debug('stopping info updater thread')
                return
            try:
                s,t = task
            except:
                self.log.warning('unexpected task {}'.format(task))
                continue
            if s == 'min':
                self._minIntegrationTime = t
                if self._minIntegrationTimeChanged is not None:
                    self._minIntegrationTimeChanged()
            elif s == 'max':
                self._maxIntegrationTime = t
                if self._maxIntegrationTimeChanged is not None:
                    self._maxIntegrationTimeChanged()
            elif s == 'current':
                c,t = t
                self._currentIntegrationTime[c] = t
                if self._currentIntegrationTimeChanged is not None:
                    self._currentIntegrationTimeChanged()
            elif s == 'auto':
                c,t = t
                self._auto_state[c] = t
                if self._auto_changed is not None:
                    self._auto_changed()
            elif s == 'spectrum':
                if t[0] == self._task_id:
                    self._spectrum = t[1]
                else:
                    self.log.error('expected acquisition {} got {}'.format(str(self._task_id),str(t[0])))
                    self._spectrum = None
                    self._task_id = None
                self._have_spectrum.set()
            else:
                self.log.warning('unknown spec {}={}'.format(s,t))
                continue
        
    @piccoloGET(parse_path=True)
    def get_current_time(self,channel):
        if channel not in self._channels:
            raise RuntimeError('unknown channel {}'.format(channel))
        return self._currentIntegrationTime[channel]
    @piccoloPUT(parse_path=True)
    def set_current_time(self,channel,t):
        if self._busy.locked():
            raise Warning('spectrometer is busy')
        self._tQ.put(('current',channel,t))
        result = self._rQ.get()
        if result != 'ok':
            raise RuntimeError(result)
    @piccoloChanged
    def callback_current_time(self,cb):
        self._currentIntegrationTimeChanged = cb
        
    @piccoloGET
    def get_min_time(self):
        return self._minIntegrationTime
    @piccoloPUT
    def set_min_time(self,t):
        if self._busy.locked():
            raise Warning('spectrometer is busy')
        self._tQ.put(('min',t))
        result = self._rQ.get()
        if result != 'ok':
            raise RuntimeError(result)
    @piccoloChanged
    def callback_min_time(self,cb):
        self._minIntegrationTimeChanged = cb
        
    @piccoloGET
    def get_max_time(self):
        return self._maxIntegrationTime    
    @piccoloPUT
    def set_max_time(self,t):
        if self._busy.locked():
            raise Warning('spectrometer is busy')
        self._tQ.put(('max',t))
        result = self._rQ.get()
        if result != 'ok':
            raise RuntimeError(result)
    @piccoloChanged
    def callback_max_time(self,cb):
        self._maxIntegrationTimeChanged = cb

    @piccoloGET(parse_path=True)
    def get_autointegration(self,channel):
        if channel not in self._channels:
            raise RuntimeError('unknown channel {}'.format(channel))
        return self._auto_state[channel]
    @piccoloChanged
    def callback_autointegration(self,cb):
        self._auto_changed = cb

    @piccoloGET
    def status(self):
        """return status of shutter

        :return: *busy* if recording or *idle*"""

        if self._busy.locked():
            return 'busy'
        else:
            return 'idle'

    def start_acquisition(self):
        """start acquiring a spectrum"""
        if self._busy.locked():
            raise Warning('spectrometer is busy')
        if self._task_id is not None:
            raise Warning('spectrum not collected yet')
        task_id = uuid.uuid1()
        self._tQ.put(('start_acquisition',task_id))
        result = self._rQ.get()
        if result != 'ok':
            raise RuntimeError(result)
        self._task_id = task_id

    def get_spectrum(self):
        """get the spectrum associated with the last acquisition"""
        if self._busy.locked():
            # the spectrometer is busy wait until it is finished
            msg='busy, waiting until spectrum {} is available'
            timeout = None
        else:
            msg='idle, waiting at most 5 seconds for spectrum {}'
            timeout = 5
        self.log.debug(msg.format(self._task_id))
        if not self._have_spectrum.wait(timeout):
            self.log.error('got no spectrum {}'.format(str(self._task_id)))
        self._task_id = None
        return self._spectrum

class PiccoloSpectrometers(PiccoloBaseComponent):
    """manage the spectrometers"""
    
    NAME = "spectrometer"

    def __init__(self,spectrometer_cfg,channels):
        super().__init__()

        self._spectrometers = {}
        # TODO loop over spectrometers

        if len(self._spectrometers) == 0:
            for sn in spectrometer_cfg:
                sname = 'S_'+sn
                self.spectrometers[sname] = PiccoloSpectrometer(sname,channels)

        for s in self.spectrometers:
            self.coapResources.add_resource([s],self.spectrometers[s].coapResources)

    @property
    def spectrometers(self):
        return self._spectrometers

    @piccoloGET
    def get_spectrometers(self):
        spectrometers = list(self.spectrometers.keys())
        spectrometers.sort()
        return spectrometers

    # implement methods so object can act as a read-only dictionary
    def keys(self):
        return self.get_spectrometers()
    def __getitem__(self,s):
        return self.spectrometers[s]
    def __len__(self):
        return len(self.spectrometers)
    def __iter__(self):
        for s in self.keys():
            yield s
    def __contains__(self,s):
        return s in self.spectrometers
        
if __name__ == '__main__':
    from .piccoloLogging import *
    from pprint import pprint
    piccoloLogging(debug=True)


    if False:
        spec = PiccoloSpectrometer('test')
        spec.set_current_time(2000)
        spec.start_acquisition()
        pprint(spec.get_spectrum())
        spec.stop()
    else:
        import asyncio
        import aiocoap.resource as resource
        import aiocoap

        specs = PiccoloSpectrometers(['test1','test2'],['up','down'])
        
        root = resource.Site()
        root.add_resource(*specs.coapSite)
        root.add_resource(('.well-known', 'core'),
                          resource.WKCResource(root.get_resources_as_linkheader))
        asyncio.Task(aiocoap.Context.create_server_context(root))

        asyncio.get_event_loop().run_forever()


