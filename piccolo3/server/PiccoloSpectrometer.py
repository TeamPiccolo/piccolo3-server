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
from piccolo3.common import PiccoloSpectrum, PiccoloSpectrometerStatus
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
from scipy.signal import find_peaks

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

        self._serial = name
        
        # set to true to create dummy spectra
        self._dummy_spectra = False
        
        # the integration times
        self._currentIntegrationTime = {}
        self._auto = {}
        self._channels = channels
        self._calibration = calibration
        for c in self.channels:
            self._currentIntegrationTime[c] = None
            self._auto[c] = None

        self._haveTEC = None
            
        self._meta = None
            
        self._maxIntegrationTime = None
        self._minIntegrationTime = None

        self._spec = None
        self._status = None
        self.status = PiccoloSpectrometerStatus.DISCONNECTED

        self.minIntegrationTime = 0
        self.maxIntegrationTime = 10000
        for c in self.channels:
            self.set_currentIntegrationTime(c,self.minIntegrationTime)
            self.set_auto(c,'n')

    @property
    def status(self):
        return self._status
    @status.setter
    def status(self,s):
        assert isinstance(s,PiccoloSpectrometerStatus)
        self._status = s
        self.info.put(('status',s))
            
    def connect(self):
        if self.status != PiccoloSpectrometerStatus.DISCONNECTED:
            self.log.warning('already connected')
        else:
            if self.serial.startswith('dummy_'):
                self.log.info('using dummy spectrometer %s'%self.serial)
                self._dummy_spectra = True
                self._spec = 'dummy'
            else:
                self.log.info('trying to connect to spectrometer %s'%self.serial)
                self.status = PiccoloSpectrometerStatus.CONNECTING

                next = time.time()
                while True:
                    try:
                        self._spec = sb.Spectrometer.from_serial_number(serial=self.serial)
                        break
                    except:
                        now = time.time()
                        if now>next:
                            self.log.warning('failed to open spectrometer %s'%self.serial)
                            next = now+5
                    # see if we get shutdown signal
                    if self.get_task(timeout=1) == 'shutdown':
                        # reinjecting shutdown
                        self.tasks.put(None)
                        return

                self.log.info('opening device')
                self._spec.open()

                self._meta = None
            self.log.info('connected to spectrometer %s'%self.serial)
            self.status = PiccoloSpectrometerStatus.IDLE
            self.minIntegrationTime = 0

    def disconnect(self):
        if self.status < PiccoloSpectrometerStatus.IDLE:
            self.log.warning('spectrometer is not connected')
        else:
            self.log.info('disconnecting spectrometer {}'.format(self.serial))
            if not self.is_dummy:
                try:
                    self.spec.close()
                except Exception as e:
                    self.log.error(e)
            self._spec = None
            self.status = PiccoloSpectrometerStatus.DISCONNECTED
            
    @property
    def is_dummy(self):
        if self.status < PiccoloSpectrometerStatus.IDLE:
            self.log.warning('spectrometer not ready')
            return True
        return self._spec == 'dummy'
    
    @property
    def spec(self):
        self.check_ready()
        return self._spec

    def check_ok(self):
        if self.status>PiccoloSpectrometerStatus.CONNECTING and not self.is_dummy and not self._spec._dev.is_open:
            self.status = PiccoloSpectrometerStatus.DISCONNECTED
            self._spec = None
            self.log.warning('spectrometer {} disappeared'.format(self.serial))
            return False
        else:
            return True

    def check_ready(self):
        if not self.check_ok():
            raise RuntimeError('spectrometer {} disappeared'.format(self.serial))
        if self.status < PiccoloSpectrometerStatus.IDLE:
            raise RuntimeError('spectrometer {} not ready'.format(self.serial))
        
    def stop(self):
        self.disconnect()

    @property
    def serial(self):
        return self._serial
            
    @property
    def dummy_spectra(self):
        return self._dummy_spectra
            
    @property
    def channels(self):
        return self._channels

    @property
    def haveTEC(self):
        if self._haveTEC is None:
            if self.is_dummy:
                self._haveTEC = False
                self.log.debug('dummy spectrometers have no TEC')
            else:
                self._haveTEC = False
                if 'thermo_electric' in self.spec.features and len(self.spec.features['thermo_electric']) > 0:
                    self._haveTEC = True
        return self._haveTEC

    @property
    def currentTemperature(self):
        if self.haveTEC:
            return self.spec.f.thermo_electric.read_temperature_degrees_celsius()
    
    @property
    def meta(self):
        if self._meta is None:
            if self.is_dummy:
                self._meta = {
                    'SerialNumber': self.name,
                    'WavelengthCalibrationCoefficients': [0,1,0,0],
                    'DarkPixels': [],
                    'NonlinearityCorrectionCoefficients': [0,1,0.0],
                    'SaturationLevel' : 200000,
                }
            else:
                # fit a polynomial to the wavelengths
                wavelengths = self.spec.wavelengths()
                coeff = numpy.polyfit(numpy.arange(len(wavelengths)),wavelengths,3)
                self._meta = {
                    'SerialNumber': self.spec.serial_number,
                    'WavelengthCalibrationCoefficients': list(coeff[::-1]),
                    'DarkPixels': list(self.spec.f.spectrometer.get_electric_dark_pixel_indices()),
                    'NonlinearityCorrectionCoefficients': list(self.spec._nc.coeffs[::-1]),
                    'SaturationLevel' : self.spec.max_intensity,
                }
            self._meta['IntegrationTimeUnits'] = 'milliseconds'
            self._meta['TemperatureEnabled'] = False
            self._meta['Temperature'] = None
            self._meta['TemperatureUnits'] = 'degrees Celcius'
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
        if not self.is_dummy:
            t = max(self.spec.minimum_integration_time_micros/1000.,t)
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
        if task[0] == 'connect':
            self.connect()
        elif task[0] == 'disconnect':
            self.disconnect()
        elif task[0] == 'haveTEC':
            self.results.put(self.haveTEC)
        elif task[0] == 'currentTemp':
            self.results.put(self.currentTemperature)
        elif task[0] == 'enableTEC':
            result = 'ok'
            try:
                self.spec.f.thermo_electric.enable_tec(task[1])
                if task[1]:
                    self.log.info('TEC enabled')
                else:
                    self.log.info('TEC disenabled')
            except Exception as e:
                result = str(e)
            self.results.put(result)
        elif task[0] == 'targetTemp':
            result = 'ok'
            try:
                self.spec.f.thermo_electric.set_temperature_setpoint_degrees_celsius(task[1])
                self.log.info('setting target temperature to {} degC'.format(task[1]))
            except Exception as e:
                result = str(e)
            self.results.put(result)
        elif task[0] == 'current':
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
                self.results.put('channel {} is unknown'.format(channel))
                return
            try:
                self.check_ready()
            except Exception as e:
                self.results.put(str(e))
                return
            dark = task[2]
            task_id = task[3]
            self.results.put('ok')
            self.status = PiccoloSpectrometerStatus.RECORDING
            try:
                self._acquire_spectrum(channel,dark,task_id)
            except Exception as e:
                self.log.error('during acquisition: {}'.format(e))
            self.status = PiccoloSpectrometerStatus.IDLE
            
        elif task[0] == 'autointegration':
            channel = task[1]
            if channel not in self.channels:
                self.results.put('channel {} is unknown'.format(channel))
                return
            try:
                self.check_ready()
            except Exception as e:
                self.results.put(str(e))
                return
            target = task[2]
            self.results.put('ok')

            if self.is_dummy:
                self.log.warning('no spectrometer')
                self.set_auto(channel,'f')
                return
            
            self.status = PiccoloSpectrometerStatus.AUTOINTEGRATING
            try:
                self._autointegrate(channel,target)
            except  Exception as e:
                self.set_auto(channel,'f')
                self.log.error('during acquisition: {}'.format(e))
            self.status = PiccoloSpectrometerStatus.IDLE
        else:
            result = 'unkown task: {}'.format(task)
            self.results.put(result)

    def _autointegrate(self,channel,target,target_tolerance = 10.,num_attempts = 5):
        self.log.info("start autointegration: channel {}, target {}%, current integration time {}".format(channel,target, self.get_currentIntegrationTime(channel)))

        delta = 100.
        target_intensity = target/100.*self.meta['SaturationLevel']
        for i in range(num_attempts):
            self.log.info('autointegration attempt %d/%d'%(i,num_attempts))
            times = []
            max_pixels = []
            success = False
            auto_time = None
            test_times =  list(numpy.logspace(numpy.log10(self.minIntegrationTime),numpy.log10(self.maxIntegrationTime),20))
            # first try current integration time
            test_times.insert(0,self.get_currentIntegrationTime(channel))

            for i in range(len(test_times)):
                integration_time = test_times[i]
                max_pixel = self._get_max(integration_time)
                if max_pixel > 0.9*self.meta['SaturationLevel']:
                    if i==0:
                        continue
                    else:
                        break

                times.append(integration_time)
                max_pixels.append(max_pixel)

                auto_fit = self._fit_autointegration(times,max_pixels,target_intensity)
                if auto_fit is None:
                    continue

                auto_time, max_pixel, percentage = auto_fit

                if abs(percentage)<target_tolerance or abs(auto_time-self.maxIntegrationTime) < 1e-6:
                    # success
                    self.set_auto(channel,'s')
                    self.set_currentIntegrationTime(channel,auto_time,reset_auto = False)
                    success = True
                    break

                if max_pixel < 0.9*self.meta['SaturationLevel']:
                    # never mind, use results for fitting line
                    times.append(auto_time)
                    max_pixels.append(max_pixel)

            if success:
                break
        else:
            self.log.error('failed to autointegrate')
            self.set_auto(channel,'f')

        self.log.info("finished autointegration: channel {}, current integration time {}".format(channel,self.get_currentIntegrationTime(channel)))

    def _acquire_spectrum(self,channel,dark,task_id):
        self.log.info("acquisition {}: channel {}, integration time {}".format(str(task_id),channel,self.get_currentIntegrationTime(channel)))
        
        # create new spectrum instance
        spectrum = PiccoloSpectrum()
        if dark:
            spectrum.setDark()
        else:
            spectrum.setLight()
        spectrum.setDirection(channel)

        # record data

        if self.is_dummy:
            if self.dummy_spectra:
                # If spectrometer is None, then simulate a spectrometer, for
                # testing purposes.
                time.sleep(self.get_currentIntegrationTime(channel)/1000.)
                pixels = list(range(100))
            else:
                self.info.put(('spectrum',(task_id,None)))
                return
        else:
            pixels = self._get_spectrum(self.get_currentIntegrationTime(channel))
            spectrum['Temperature'] = self.currentTemperature

        spectrum.update(self.meta)
        spectrum['IntegrationTime'] = self.get_currentIntegrationTime(channel)
        if channel in self._calibration:
            spectrum['WavelengthCalibrationCoefficientsPiccolo'] = self._calibration[channel]
        spectrum.pixels = pixels

        self.info.put(('spectrum',(task_id,spectrum)))
            
    def _get_spectrum(self,integration_time):
        integration_time = max(integration_time,self.minIntegrationTime)
        integration_time = min(integration_time,self.maxIntegrationTime)
        self.spec.integration_time_micros(integration_time * 1000.)
        time.sleep(0.1)
        pixels = self.spec.intensities()
        pixels = self.spec.intensities()
        self.spec.integration_time_micros(self.minIntegrationTime* 1000.)
        self.log.debug('recorded spectrum t={}, max intensity={}'.format(integration_time,max(pixels)))
        return pixels
                       
            
    def _get_max(self,integration_time):
        pixels = self._get_spectrum(integration_time)
        if True:
            try:
                peaks, properties = find_peaks(pixels,width=5)
                max_pixel = max(properties['prominences'])
            except:
                max_pixel = max(pixels)
        else:
            max_pixel = max(pixels)
        self.log.debug('max intensity at t={},max={}'.format(integration_time, max_pixel))
        if False:
            self.log.debug(properties['prominences'])
        return max_pixel    

    def _fit_autointegration(self,times,intensities,target_intensity):

        if len(times) < 2:
            return
        
        coeff = numpy.polyfit(times,intensities,1)
        self.log.debug('found line {}*t+{}'.format(coeff[0],coeff[1]))
        auto_time = (target_intensity-coeff[1])/coeff[0]

        auto_time = max(auto_time,self.minIntegrationTime)
        auto_time = min(auto_time,self.maxIntegrationTime)

        max_pixel = self._get_max(auto_time)

        percentage = abs(max_pixel-target_intensity)/target_intensity*100.
        self.log.info('test integration time: t={}, max={}, percentage={}'.format(
            auto_time, max_pixel,percentage))
        return (auto_time, max_pixel, percentage)
            
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

        self._status = PiccoloSpectrometerStatus.NO_WORKER
        self._status_changed = None
        
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

        # TEC feature
        self._haveTEC = None
        self._TECenabled = None
        self._TECenabledChanged = None
        self._currentTemperature = None
        self._targetTemperature = None
        self._targetTemperatureChanged = None
                
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
        self.connect()
        self.log.info('started')

    def stop(self):
        # send poison pill to worker
        self.log.info('shutting down')
        self._tQ.put(None)

    def connect(self):
        self._tQ.put(('connect',None))        
    def disconnect(self):
        self._tQ.put(('disconnect',None))        
        
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
            elif s== 'status':
                self._status = t
                if self._status_changed is not None:

                    self._status_changed()
            else:
                self.log.warning('unknown spec {}={}'.format(s,t))
                continue

    @property
    def haveTEC(self):
        if self._haveTEC is None:
            #self.check_idle()
            self._tQ.put(('haveTEC',None))
            self._haveTEC = self._rQ.get()
        return self._haveTEC
    @piccoloGET
    def get_haveTEC(self):
        return self.haveTEC        
    @piccoloGET
    def get_current_temperature(self):
        if not self.haveTEC:
            raise RuntimeError('device has not TEC')
        try:
            self.check_idle()
            self._tQ.put(('currentTemp',))
            t = self._rQ.get()
            self._currentTemperature = t
        except Exception as e:
            self.log.warn(str(e))
            t = self._currentTemperature
        return t

    @property
    def TECenabled(self):
        if not self.haveTEC:
            return False
        return self._TECenabled
    @TECenabled.setter
    def TECenabled(self,state):
        if self.haveTEC and state is not self._TECenabled:
            self.check_idle()
            self._tQ.put(('enableTEC',state))
            result = self._rQ.get()
            if result != 'ok':
                raise RuntimeError(result)
            self._TECenabled = state
            if self._TECenabledChanged is not None:
                self._TECenabledChanged()
    @piccoloGET
    def get_TECenabled(self):
        return self.TECenabled
    @piccoloPUT
    def set_TECenabled(self,state):
        self.TECenabled = state
    @piccoloChanged
    def callback_TECenabled(self,cb):
        self._TECenabledChanged = cb

    @property
    def target_temperature(self):
        return self._targetTemperature
    @target_temperature.setter
    def target_temperature(self,t):
        if self._targetTemperature is None or abs(self._targetTemperature-t)>1e-5:
            self.check_idle()
            self._tQ.put(('targetTemp',t))
            result = self._rQ.get()
            if result != 'ok':
                raise RuntimeError(result)
            self._targetTemperature = t
            if self._targetTemperatureChanged is not None:
                self._targetTemperatureChanged()
    @piccoloGET
    def get_target_temperature(self):
        return self.target_temperature
    @piccoloPUT
    def set_target_temperature(self,t):
        self.target_temperature = t
    @piccoloChanged
    def callback_target_temperature(self,cb):
        self._targetTemperatureChanged = cb
    
    @piccoloGET(parse_path=True)
    def get_current_time(self,channel):
        if channel not in self._channels:
            raise RuntimeError('unknown channel {}'.format(channel))
        return self._currentIntegrationTime[channel]
    @piccoloPUT(parse_path=True)
    def set_current_time(self,channel,t):
        self.check_idle()
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
        self.check_idle()
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
        self.check_idle()
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

    @property
    def status(self):
        if not self._spectrometer.is_alive():
            self._status = PiccoloSpectrometerStatus.NO_WORKER        
        return self._status
    @piccoloGET
    def get_status(self):
        """return status of shutter

        :return: *busy* if recording or *idle*"""

        return self.status
    @piccoloChanged
    def callback_status(self,cb):
        self._status_changed = cb
    def check_idle(self):
        if self.status != PiccoloSpectrometerStatus.IDLE:
            raise Warning('status of spectrometer %s is %s'%(self.name,self.status))

    def autointegrate(self,channel,target=80.):
        """start autointegration"""
        self.check_idle()
        if target<0 or target > 100:
            raise RuntimeError('target out of range 0<%s<100'%target)
        self._tQ.put(('autointegration',channel,target))
        result = self._rQ.get()
        if result != 'ok':
            raise RuntimeError(result)

    def start_acquisition(self,channel,dark=False):
        """start acquiring a spectrum"""
        self.check_idle()
        if len(self._task_id)>0:
            raise Warning('spectrum not collected yet')
        task_id = uuid.uuid1()
        self._task_id.append(task_id)        
        self._tQ.put(('start_acquisition',channel,dark,task_id))
        result = self._rQ.get()
        if result != 'ok':
            self._task_id.pop()
            raise RuntimeError(result)

    def _get_spectrum(self,tID,status):
        s = self._spectra[tID]
        del self._spectra[tID]
        self._task_id.popleft()
        self.log.info('got spectrum {} ({})'.format(tID,status))
        if s.isSaturated:
            self.log.warning('spectrum {} is saturated'.format(tID))
        return s
        
    def get_spectrum(self):
        """get the spectrum associated with the last acquisition"""
        if self.status == 'disconnected':
            raise Warning('spectrometer %s is disconnected'%self.name)
        if len(self._task_id) > 0:
            tID = self._task_id[0]
            if tID in self._spectra:
                return self._get_spectrum(tID,'a')
        if self.status == PiccoloSpectrometerStatus.DISCONNECTED:
            raise RuntimeError('spectrometer {} disconnected'.format(self.name))
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
        return self._get_spectrum(tID,'w')

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
                if self.spectrometers[sname].haveTEC:
                    self.spectrometers[sname].TECenabled = spectrometer_cfg[sn]['fan']
                    self.spectrometers[sname].target_temperature = spectrometer_cfg[sn]['detectorSetTemperature']

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


    if False:
        async def test():
            spec1 = PiccoloSpectrometer('QEP01651',['up','down'],{})
            spec2 = PiccoloSpectrometer('USB2+H13525',['up','down'],{})
            print (spec1.status,spec2.status)
            await asyncio.sleep(1)
            print (spec1.status,spec2.status)
            for i in range(2):
                await asyncio.sleep(1)
                print ('c',i,spec1.status,spec2.status)

            spec1.set_current_time('up',2000)
            spec2.set_current_time('up',2000)
            #spec1.disconnect()
            try:
                spec1.start_acquisition('up')
            except Exception as e:
                print(e)
            try:
                spec2.start_acquisition('up')
            except Exception as e:
                print(e)
            for i in range(5):
                await asyncio.sleep(1)
                print ('r',i,spec1.status,spec2.status)
            try:
                s = spec1.get_spectrum().as_dict()
                pprint(s)
            except Exception as e:
                print(e)
            try:
                s = spec2.get_spectrum().as_dict()
                pprint(s)
            except Exception as e:
                print(e)
                
            #spec1.disconnect()
            #spec2.disconnect()
            for i in range(20):
                await asyncio.sleep(1)
                print ('d',i,spec1.status,spec2.status)
            spec1.connect()
            spec2.connect()
            for i in range(5):
                await asyncio.sleep(1)
                print ('c',i,spec1.status,spec2.status)
            spec1.stop()
            spec2.stop()
            await asyncio.sleep(1)
            print (spec1.status,spec2.status)
        asyncio.run(test())
    elif True:
        async def test():
            spec = PiccoloSpectrometer('QEP01651',['up','down'],{}) # QEP00981
            await asyncio.sleep(1)
            print ('start',spec.get_current_time('up'))
            print (spec.status)
            spec.set_max_time(5000)
            spec.autointegrate('up')
            await asyncio.sleep(1)

            while spec.status > PiccoloSpectrometerStatus.IDLE:
                await asyncio.sleep(1)
                print (spec.status)
            print ('done',spec.get_current_time('up'))
            spec.stop()
            await asyncio.sleep(1)

        from .PiccoloHardware import piccoloShutters
        for i in range(2):
            s = piccoloShutters[i]
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


