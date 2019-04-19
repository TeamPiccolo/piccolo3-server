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

__all__ = ['PiccoloScheduledJob','PiccoloScheduler']

import uuid
import logging
import datetime, pytz
from dateutil import parser

class PiccoloScheduledJob:
    """a scheduled job

    a job will only get scheduled if it is in the future
    """

    ISOFORMAT = "%Y-%m-%dT%H:%M:%S.%f%z"

    def __init__(self,at_time,interval,job,end_time=None):
        """
        :param at_time: the time at which the job should run
        :type at_time: datetime.datetime or isoformat string
        :param interval: repeated schedule job if interval is not set to None
        :type interval: datetime.timedelta or float (seconds) or None
        :param job: scheduled job object, gets returned when run method is called
        :param end_time: the time after which the job is no longer scheduled
        :type end_time: datetime.datetime or isoformat string or None
        """
        
        self._log = logging.getLogger('piccolo.scheduledjob')

        # parse scheduling specs
        if isinstance(at_time,datetime.datetime):
            self._at = at_time
        else:
            self._at = parser.parse(at_time)

        self._interval=None
        if interval!=None:
            if isinstance(interval,datetime.timedelta):
                self._interval=interval
            else:
                self._interval=datetime.timedelta(seconds=interval)

        self._end = None
        if end_time!=None:
            if isinstance(end_time,datetime.datetime):
                self._end = end_time
            else:
                self._end = parser.parse(end_time)

        self._jid = str(uuid.uuid1())
        self._job = job
        self._has_run = False
        self._suspended = False

        # check that scheduled time is not in the past
        now = datetime.datetime.now(tz=pytz.utc)
        if self._at < now and (self._end is None or self._end < now):
            self.log.warning("scheduled job is in the past")
            self._has_run = True
        if self._end is not None and self._at >= self._end:
            self.log.warning("job is scheduled for execution after the end time")
            self._has_run = True


    @property
    def log(self):
        """get the logger"""
        return self._log

    @property
    def jid(self):
        """get the ID"""
        return self._jid

    @property
    def shouldRun(self):
        """:return: True if the job has not already run and the scheduled time 
                    < now
        """
        if self._has_run or self.suspended:
            return False
        else:
            return self._at < datetime.datetime.now(tz=pytz.utc)

    @property
    def suspended(self):
        """whether the job is suspended"""
        return self._suspended

    @property
    def at_time(self):
        """ the time at which the job should run"""
        return self._at

    @property
    def end_time(self):
        """get time after which the job should not be run anymore"""
        return self._end

    @property
    def interval(self):
        """the interval at which the job should be repeated or None for a single job"""
        return self._interval
        
    def __lt__(self,other):
        assert isinstance(other,PiccoloScheduledJob)
        return self.at_time < other.at_time

    def suspend(self,suspend=True):
        """suspend job"""
        self._suspended = suspend

    def unsuspend(self,suspend=False):
        """unsuspend job"""
        self._suspended = suspend        

    @property
    def as_dict(self):
        jobDict = {}
        jobDict['job'] = self._job
        for k in ['jid','suspended']: #,'at_time','end_time','interval','suspended']:
            jobDict[k] = getattr(self,k)
        for k in ['at_time','end_time']:
            dt = getattr(self,k)
            if dt!=None:
                jobDict[k] = dt.strftime("%Y-%m-%dT%H:%M:%S%z")
            else:
                jobDict[k] = ''
        if self.interval != None:
            jobDict['interval'] = self.interval.total_seconds()
        else:
            jobDict['interval'] = 0
        return jobDict

    def run(self):
        """run the job

        check if the job should be run, increment scheduled time if applicable"""
        if not self.shouldRun:
            return None
        if self._interval == None:
            self.log.debug("final run of job {0}".format(self.jid))
            self._has_run = True
        else:
            n = (datetime.datetime.now(tz=pytz.utc)-self._at).total_seconds()//self._interval.total_seconds()+1
            if n>1:
                self.log.debug("job {0}: fast forwarding {1} times".format(self.jid,n))
                dt = datetime.timedelta(seconds=n*self._interval.total_seconds())
            else:
                dt = self._interval
            self._at = self._at + dt
            self.log.debug("job {0}: incrementing scheduled time".format(self.jid))
            if self._end!= None and self._at >= self._end:
                self._has_run = True
                self.log.debug("job {0}: new time is beyond end time".format(self.jid))

        return self._job

class PiccoloScheduler:
    """the piccolo scheduler holds the scheduled jobs"""

    def __init__(self):

        self._log = logging.getLogger('piccolo.scheduler')
        
        self._jobs = {}

        self._loggedQuietTime = False
        
        self._quietStart = None
        self._quietEnd = None

    @property
    def log(self):
        """get the logger"""
        return self._log
        
    @staticmethod
    def _parseTime(t):
        if t is None or isinstance(t,datetime.time):
            return t
        else:
            return datetime.datetime.strptime(t,"%H:%M:%S").time().replace(tzinfo=pytz.utc)

    @property
    def quietStart(self):
        return self._quietStart
    @quietStart.setter
    def quietStart(self,t):
        self._quietStart = self._parseTime(t)

    @property
    def quietEnd(self):
        return self._quietEnd
    @quietEnd.setter
    def quietEnd(self,t):
        self._quietEnd = self._parseTime(t)

    @property
    def inQuietTime(self):
        inQuietTime = False
        if self._quietStart and self._quietEnd:
            now = datetime.datetime.now(tz=pytz.utc)
            qs = datetime.datetime.combine(now.date(),self.quietStart)
            qe = datetime.datetime.combine(now.date(),self.quietEnd)
            if qs > qe:
                # add a day to account for day boundary
                qe = qe + datetime.timedelta(1)
            if qs < now < qe:
                inQuietTime = True
        return inQuietTime
        
    def add(self,at_time,job,interval=None,end_time=None):
        """add a new job

        :param at_time: the time at which the job should run
        :type at_time: datetime.datetime
        :param job: object returned when scheduled job is run
        :param interval: repeated schedule job if interval is not set to None
        :type interval: datetime.timedelta
        :param end_time: the time after which the job is no longer scheduled
        :type end_time: datetime.datetime or None
        """

        job = PiccoloScheduledJob(at_time,interval,job,end_time=end_time)

        self._jobs[job.jid] = job

        return job

    @property
    def runable_jobs(self):
        """get iterator over runable jobs"""
        if self.inQuietTime:
            if not self._loggedQuietTime:
                self.log.info("quiet time started, not scheduling any jobs")
                self._loggedQuietTime = True
            return []
        else:
            if self._loggedQuietTime:
                self.log.info("quiet time stopped, scheduling jobs again")
                self._loggedQuietTime = False
            return (job for job in self._jobs.values() if job.shouldRun)

    def _suspend(self,jid,state):
        """suspend or unsuspend particular job"""

        self._jobs[jid].suspend(suspend=state)

    def suspend(self,jid):
        """suspend job
        
        :param jid: id of job to suspend
        :type jid: int"""
        self._suspend(jid,True)

    def unsuspend(self,jid):
        """unsuspend job
        
        :param jid: id of job to unsuspend
        :type jid: int"""
        self._suspend(jid,False)


    # implement methods so object can act as a read-only dictionary
    def keys(self):
        return self._jobs.keys()
    def __getitem__(self,s):
        return self._jobs[s]
    def __len__(self):
        return len(self._jobs)
    def __iter__(self):
        for s in self.keys():
            yield s
    def __contains__(self,s):
        return s in self._jobs
        
if __name__ == '__main__':
    from piccolo3.common import piccoloLogging
    import time

    piccoloLogging(debug=True)

    ps = PiccoloScheduler()

    now = datetime.datetime.now(tz=pytz.utc)
    
    ps.add(now+datetime.timedelta(seconds=5),"hello")
    task2 = ps.add(now+datetime.timedelta(seconds=10),"hello2",interval=datetime.timedelta(seconds=5))
    ps.add(now+datetime.timedelta(seconds=8),"hello3",interval=datetime.timedelta(seconds=3),end_time=datetime.datetime.now(tz=pytz.utc)+datetime.timedelta(seconds=20))

    ps.add(now-datetime.timedelta(seconds=5),"this should not be scheduled as in the past")


    qs = now+datetime.timedelta(seconds=60)
    qe = now+datetime.timedelta(seconds=80)

    
    ps.quietStart = qs.timetz()
    ps.quietEnd = qe.timetz()

    print (ps.keys())
    
    for i in range(0,100):
        for job in ps.runable_jobs:
            print (job.jid, job.at_time, job.run())
        time.sleep(1)
        if i==27:
            ps.suspend(task2.jid)
        if i==41:
            ps.unsuspend(task2.jid)
        print (i)
