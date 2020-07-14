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

__all__ = ['PiccoloThread','PiccoloWorkerThread']

import threading
import logging
from queue import Empty

class PiccoloThread(threading.Thread):
    """base piccolo threading class"""

    def __init__(self,name,daemon=True):
        super().__init__()

        self.name = name
        self.daemon = daemon
        self._log = logging.getLogger('piccolo.{}'.format(self.name))
        self.log.info('initialising piccolo thread')
        
    @property
    def log(self):
        """the worker log"""
        return self._log

class PiccoloWorkerThread(PiccoloThread):
    """base class for handling piccolo worker threads"""

    def __init__(self,name,busy, tasks, results,info,daemon=True):
        """initialise worker thread

        :param name: a descriptive name for the worker thread, also used for logging
        :type name: str
        :param busy: a "lock" which prevents using the spectrometer when it is busy
        :type busy: thread.lock
        :param tasks: a queue into which tasks will be put
        :type tasks: Queue.Queue
        :param results: the results queue from where results will be collected
        :type results: Queue.Queue
        :param info: queue for reporting back info
        :type info: Queue.Queue
        :param daemon: boolean value indicating whether this thread is a daemon thread (True) or not (False)
        """

        super().__init__(name,daemon=daemon)

        self._busy = busy
        self._tQ = tasks
        self._rQ = results
        self._iQ = info

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

    def get_task(self,block=True, timeout=None):
        try:
            task = self.tasks.get(block=block,timeout=timeout)
        except Empty:
            return

        if task is None:
            task = 'shutdown'
        
        self.log.debug('got task {}'.format(task))

        return task

    def stop(self):
        pass
    
    def run(self):
        while True:
            # wait for a new task from the task queue
            task = self.get_task()

            if self.busy.locked():
                self.results.put('worker {} is busy'.format(self.name))
                continue
            self.busy.acquire()
                        
            if task == 'shutdown':
                # The worker thread can be stopped by putting a None onto the task queue.
                self.info.put(None)
                self.stop()
                self.log.info('Stopped worker thread')
                return

            self.process_task(task)

            self.busy.release()

    def process_task(self,task):
        """process task"""
        raise NotImplementedError
