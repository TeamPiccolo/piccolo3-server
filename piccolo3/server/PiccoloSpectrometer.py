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

import asyncio
from piccolo3.common import PiccoloSpectrum
from .PiccoloComponent import PiccoloBaseComponent, PiccoloNamedComponent, piccoloGET, piccoloPUT, piccoloChanged
from .PiccoloWorkerThreads import PiccoloWorkerThread
import threading
from queue import Queue, Empty
import janus
import logging
import uuid
import time
from collections import deque
import numpy

import seabreeze.spectrometers as sb

class PiccoloSpectrometerWorker(PiccoloWorkerThread):
    """Spectrometer worker thread object. The worker thread performs assigned
    tasks in the background and holds on to the results until they are
    picked up."""

    def __init__(self, name, channels, calibration, busy, tasks, results,info,daemon=True):
        """Initialize the worker thread.

        Note: calling __init__ does not start the thread, a subsequent call to
        start() is needed to start the thread.

        :param name: a descriptive name for the spectrometer.
        :type name: str
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
        
        super().__init__('spectrometer_worker.{}'.format(name),busy, tasks, results,info,daemon=daemon)

        # the integration times
        self._currentIntegrationTime = {}
        self._auto = {}
        self._channels = channels
        self._calibration = calibration
        for c in self.channels:
            self._currentIntegrationTime[c] = None
            self._auto[c] = None

        self._meta = None
            
        self._maxIntegrationTime = None
        self._minIntegrationTime = None

        try:
            self._spec = sb.Spectrometer.from_serial_number(serial=name)
        except:
            self.log.warning('failed to open spectrometer %s'%name)
            self._spec = None

        self.minIntegrationTime = 0
        self.maxIntegrationTime = 10000
        for c in self.channels:
            self.set_currentIntegrationTime(c,self.minIntegrationTime)
            self.set_auto(c,'n')
        
    @property
    def channels(self):
        return self._channels

    @property
    def meta(self):
        if self._meta is None:
            if self._spec is None:
                self._meta = {
                    'SerialNumber': self.name,
                    'WavelengthCalibrationCoefficients': [0,1,0,0],
                    'IntegrationTimeUnits': 'milliseconds',
                    'DarkPixels': [],
                    'NonlinearityCorrectionCoefficients': [0,1,0.0],
                    'SaturationLevel' : 200000,
                    'TemperatureEnabled': False,
                    'Temperature': None,
                    'TemperatureUnits': 'degrees Celcius'
                }
            else:
                # fit a polynomial to the wavelengths
                wavelengths = self._spec.wavelengths()
                coeff = numpy.polyfit(numpy.arange(len(wavelengths)),wavelengths,3)
                self._meta = {
                    'SerialNumber': self._spec.serial_number,
                    'WavelengthCalibrationCoefficients': list(coeff[::-1]),
                    'IntegrationTimeUnits': 'milliseconds',
                    'DarkPixels': list(self._spec._dark),
                    'NonlinearityCorrectionCoefficients': list(self._spec._nc.coeffs[::-1]),
                    'SaturationLevel' : 200000,
                    'TemperatureEnabled': False,
                    'TemperatureUnits': 'degrees Celcius'
                }
        return self._meta
    
    
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
        if self._spec:
            t = max(self._spec.minimum_integration_time_micros/1000.,t)
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
        
    def process_task(self,task):
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
                return
            dark = task[2]
            task_id = task[3]
            self.results.put('ok')

            self.log.info("acquisition {}: channel {}, integration time {}".format(str(task_id),channel,self.get_currentIntegrationTime(channel)))
            # create new spectrum instance
            spectrum = PiccoloSpectrum()
            if dark:
                spectrum.setDark()
            else:
                spectrum.setLight()
            spectrum.setDirection(channel)
            
            # record data

            if self._spec is None:
                # If spectrometer is None, then simulate a spectrometer, for
                # testing purposes.
                time.sleep(self.get_currentIntegrationTime(channel)/1000.)
                pixels = list(range(100))
            else:
                self._spec.integration_time_micros(self.get_currentIntegrationTime(channel)*1000.)
                for i in range(2):
                    pixels = self._spec.intensities()
                spectrum['Temperature'] = self._spec.tec_get_temperature_C()
                
            spectrum.update(self.meta)
            spectrum['IntegrationTime'] = self.get_currentIntegrationTime(channel)
            if channel in self._calibration:
                spectrum['WavelengthCalibrationCoefficientsPiccolo'] = self._calibration[channel]
            spectrum.pixels = pixels

            self.info.put(('spectrum',(task_id,spectrum)))
        elif task[0] == 'autointegration':
            channel = task[1]
            if channel not in self.channels:
                self.result.put('channel {} is unknown'.format(channel))
                return
            target = task[2]
            target_tolerance = 10.
            num_attempts = 5
            self.results.put('ok')

            self.log.info("start autointegration: channel {}, target {}%, current integration time {}".format(channel,target, self.get_currentIntegrationTime(channel)))

            delta = 100.
            for i in range(num_attempts):
                self.log.info('autointegration attempt %d/%d'%(i,num_attempts))
                times = []
                max_pixels = []
                for integration_time in numpy.logspace(numpy.log10(self.minIntegrationTime),numpy.log10(self.maxIntegrationTime),20):
                    self._spec.integration_time_micros(integration_time * 1000.)
                    pixels = self._spec.intensities()
                    pixels = self._spec.intensities()
                    max_pixel = max(pixels)
                    self.log.debug('t={},max={}'.format(integration_time, max_pixel))
                    if max_pixel > 0.9*self.meta['SaturationLevel']:
                        break
                    if max_pixel > 20000:
                        times.append(integration_time)
                        max_pixels.append(max_pixel)

                if len(times)>0:
                    coeff = numpy.polyfit(times,max_pixels,1)
                    self.log.debug('found line {}*t+{}'.format(coeff[0],coeff[1]))
                else:
                    self.log.warning('could not fit line')
                    continue

                target_intensity = target/100.*self.meta['SaturationLevel']
                
                auto_time = (target_intensity-coeff[1])/coeff[0]
                auto_time = max(auto_time,self.minIntegrationTime)
                auto_time = min(auto_time,self.maxIntegrationTime)

                self._spec.integration_time_micros(auto_time * 1000.)
                pixels = self._spec.intensities()
                pixels = self._spec.intensities()
                max_pixel = max(pixels)

                percentage = abs(max_pixel-target_intensity)/target_intensity*100.
                self.log.info('found time: t={}, max={}, percentage={}'.format(
                    auto_time, max_pixel,percentage))
                if abs(percentage)<target_tolerance or abs(auto_time-self.maxIntegrationTime) < 1e-6:
                    self.set_currentIntegrationTime(channel,auto_time,reset_auto=False)
                    self.set_auto(channel,'y')
                    break
                    
            else:
                self.log.error('failed to autointegrate')
                self.set_auto(channel,'f')
            
            self._spec.integration_time_micros(self.minIntegrationTime* 1000.)
            self.log.info("finished autointegration: channel {}, current integration time {}".format(channel,self.get_currentIntegrationTime(channel)))
        else:
            result = 'unkown task: {}'.format(task)
            self.results.put(result)
                
class PiccoloSpectrometer(PiccoloNamedComponent):
    """frontend class used to communicate with spectrometer"""

    NAME = 'spectrometer'
    
    def __init__(self,name, channels,calibration):
        """Initialize a Piccolo Spectrometer object for Piccolo Server.

        The spectromter parameter must be the Spectrometer object from the
        Piccolo Hardware module, such as OceanOpticsUSB2000Plus or
        OceanOpticsQEPro.

        name is a descriptive name for the spectrometer.

        :param name: a descriptive name for the spectrometer.
        :param channels: a list of channels
        """

        super().__init__(name)

        # the various queues
        # The lock prevents two threads using the spectrometer at the same time.
        self._busy = threading.Lock()
        self._tQ = Queue() # Task queue.
        self._rQ = Queue() # Results queue.

        loop = asyncio.get_event_loop()        
        self._iQ = janus.Queue(loop=loop) # info queue
        
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
        self._task_id = deque()
        self._spectra = {}

        # start the info updater thread
        self._uiTask = loop.create_task(self._update_info())

        # start the spectrometer worker thread
        self._spectrometer = PiccoloSpectrometerWorker(name,
                                                       channels,
                                                       calibration,
                                                       self._busy,
                                                       self._tQ, self._rQ,
                                                       self._iQ.sync_q)
        self._spectrometer.start()

    def stop(self):
        # send poison pill to worker
        self.log.info('shutting down')
        self._tQ.put(None)
        
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
                self._spectra[t[0]] = t[1]
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

    def autointegrate(self,channel,target=80.):
        """start autointegration"""
        if self._busy.locked():
            raise Warning('spectrometer is busy')
        if target<0 or target > 100:
            raise RuntimeError('target out of range 0<%s<100'%target)
        self._tQ.put(('autointegration',channel,target))
        result = self._rQ.get()
        if result != 'ok':
            raise RuntimeError(result)

    def start_acquisition(self,channel,dark=False):
        """start acquiring a spectrum"""
        if self._busy.locked():
            raise Warning('spectrometer is busy')
        if len(self._task_id)>0:
            raise Warning('spectrum not collected yet')
        task_id = uuid.uuid1()
        self._task_id.append(task_id)        
        self._tQ.put(('start_acquisition',channel,dark,task_id))
        result = self._rQ.get()
        if result != 'ok':
            self._task_id.pop()
            raise RuntimeError(result)

    def get_spectrum(self):
        """get the spectrum associated with the last acquisition"""
        if len(self._task_id) > 0:
            tID = self._task_id[0]
            if tID in self._spectra:
                s = self._spectra[tID]
                del self._spectra[tID]
                self._task_id.popleft()
                self.log.info('got spectrum {} (a)'.format(tID))
                return s
        if self._busy.locked():
            self.log.debug('busy, waiting until a spectrum is available')
            self._busy.acquire()
            self._busy.release()

        tID = self._task_id[0]
        if tID not in self._spectra:
            for i in range(50):
                time.sleep(0.1)
                if tID in self._spectra:
                    break
            else:
                raise RuntimeError('Waited 5s for spectrum {} but did not get it'.format(tID))
        s = self._spectra[tID]
        del self._spectra[tID]
        self._task_id.popleft()
        self.log.info('got spectrum {} (w)'.format(tID))
        return s

class PiccoloSpectrometers(PiccoloBaseComponent):
    """manage the spectrometers"""
    
    NAME = "spectrometer"

    def __init__(self,spectrometer_cfg,channels):
        super().__init__()

        self._channels = channels
        
        self._spectrometers = {}
        # TODO loop over spectrometers

        if len(self._spectrometers) == 0:
            for sn in spectrometer_cfg:
                sname = 'S_'+sn
                calibration = {}
                if 'calibration' in spectrometer_cfg[sn]:
                    for c in spectrometer_cfg[sn]['calibration']:
                        if 'wavelengthCalibrationCoefficientsPiccolo' in spectrometer_cfg[sn]['calibration'][c]:
                            calibration[c] = spectrometer_cfg[sn]['calibration'][c]['wavelengthCalibrationCoefficientsPiccolo']
                self.spectrometers[sname] = PiccoloSpectrometer(sn,channels,calibration)

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

    @piccoloGET
    def get_channels(self):
        return self._channels
    
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
    import asyncio
    from piccolo3.common import piccoloLogging
    from pprint import pprint
    piccoloLogging(debug=True)

    
    if True:
        async def test():
            spec = PiccoloSpectrometer('QEP00981',['up','down'],{})
            print ('start',spec.get_current_time('up'))
            spec.set_max_time(500)
            spec.autointegrate('up')

            while spec.status() == 'busy':
                await asyncio.sleep(1)
                print (spec.status())
            print ('done',spec.get_current_time('up'))
            spec.stop()

        from .PiccoloHardware import piccoloShutters
        s = piccoloShutters[0]
        s.open()
        asyncio.run(test())
        s.close()
    elif False:
        async def test():
            spec = PiccoloSpectrometer('QEP00981',['up','down'],{})
        
            spec.set_current_time('up',2000)
            spec.start_acquisition('up')
            time.sleep(0.1)
            await asyncio.sleep(5)
            s = spec.get_spectrum().as_dict()
            pprint(s)
            print ('max',max(s['Pixels']))
            spec.stop()

        from .PiccoloHardware import piccoloShutters
        s = piccoloShutters[0]
        s.open()
        asyncio.run(test())
        s.close()
    else:
        import aiocoap.resource as resource
        import aiocoap

        specs = PiccoloSpectrometers(['QEP00981','QEP00114'],['up','down'])

        def start_worker_loop(loop):
            asyncio.set_event_loop(loop)
            loop.run_forever()
        
        root = resource.Site()
        root.add_resource(*specs.coapSite)
        root.add_resource(('.well-known', 'core'),
                          resource.WKCResource(root.get_resources_as_linkheader))
        asyncio.Task(aiocoap.Context.create_server_context(root,loggername='piccolo.coap'))

        asyncio.get_event_loop().run_forever()


