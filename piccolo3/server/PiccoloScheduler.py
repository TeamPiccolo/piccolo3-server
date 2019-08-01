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

__all__ = ['PiccoloScheduler']

from .PiccoloComponent import PiccoloBaseComponent, PiccoloNamedComponent, piccoloGET, piccoloPUT, piccoloChanged
import logging
import datetime, pytz
from dateutil import parser
import json
import sqlalchemy
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

class DateTimeTZ(sqlalchemy.TypeDecorator):
    """a DateTime object with utc time zone"""
    impl = sqlalchemy.DateTime

    def process_result_value(self, value, dialect):
        if value is not None:
            return value.replace(tzinfo=pytz.utc)

class JSONString(sqlalchemy.TypeDecorator):
    """encode/decode an object as a JSON string"""
    
    impl = sqlalchemy.VARCHAR

    def process_bind_param(self, value, dialect):
        if value is not None:
            value = json.dumps(value)

        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            value = json.loads(value)
        return value


class Settings(Base):
    __tablename__ = 'settings'

    key = sqlalchemy.Column(sqlalchemy.String,primary_key=True)
    value = sqlalchemy.Column(sqlalchemy.String)
    
class QuietTime(Base):

    __tablename__ = 'quiettime'

    label = sqlalchemy.Column(sqlalchemy.String,primary_key=True)
    time = sqlalchemy.Column(sqlalchemy.Time)
    

class PiccoloScheduledJob(Base):
    """a scheduled job

    a job will only get scheduled if it is in the future
    """
    
    __tablename__ = 'jobs'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    job = sqlalchemy.Column(JSONString)
    start_time = sqlalchemy.Column(DateTimeTZ(timezone=True))
    end_time = sqlalchemy.Column(DateTimeTZ(timezone=True), default=None)
    interval = sqlalchemy.Column(sqlalchemy.Interval, default=None)
    suspended = sqlalchemy.Column(sqlalchemy.Boolean, default=False)

    def suspend(self):
        self.suspended = True

    def unsuspend(self):
        self.suspended = False

    def tolist(self):
        if self.end_time is not None:
            et = self.end_time
        else:
            et = None
        return [
            self.id,
            self.job,
            str(self.start_time),
            et,
            self.interval,
            self.suspended]

class PiccoloScheduler(PiccoloBaseComponent):
    """the piccolo scheduler holds the scheduled jobs"""

    NAME = "scheduler"
    
    def __init__(self,db='sqlite:///:memory:'):

        super().__init__()
        
        engine = sqlalchemy.create_engine(db)
        Session = sessionmaker(bind=engine)
        self._session = Session()
        Base.metadata.create_all(engine)

        self._loggedQuietTime = False

        self._quietTimeEnabled = self.session.query(Settings).filter(Settings.key == 'quiet_time_enabled').one_or_none()
        if self._quietTimeEnabled is None:
            self._quietTimeEnabled = Settings(key='quiet_time_enabled',value='False')
            self.session.add(self._quietTimeEnabled)
        self._quietTimeEnabled_changed = False
        
        self._quietStart = self.session.query(QuietTime).filter(QuietTime.label == 'start').one_or_none()
        if self._quietStart is None:
            self._quietStart = QuietTime(label='start',time=self._parseTime('22:00:00'))
            self.session.add(self._quietStart)
        self._quietStart_changed = None
            
        self._quietEnd = self.session.query(QuietTime).filter(QuietTime.label == 'end').one_or_none()
        if self._quietEnd is None:
            self._quietEnd = QuietTime(label='end',time=self._parseTime('04:00:00'))
            self.session.add(self._quietEnd)
        self._quietEnd_changed = None

        self._jobs_changed = None

    @staticmethod
    def _parseTime(t):
        if t is None or isinstance(t,datetime.time):
            return t
        else:
            try:
                t = datetime.datetime.strptime(t,"%H:%M:%S%z").timetz()
            except:
                t = datetime.datetime.strptime(t,"%H:%M:%S").time().replace(tzinfo=pytz.utc)
            return t

    @staticmethod
    def now():
        return datetime.datetime.now(tz=pytz.utc)

    @piccoloGET
    def get_quietTimeEnabled(self):
        if self._quietTimeEnabled.value == 'True':
            return True
        else:
            return False
    @piccoloPUT
    def set_quietTimeEnabled(self,e):
        if isinstance(e,bool):
            e = str(e)
        if not e in ['True','False']:
            raise ValueError('unexpected value for quietTimeEnabled %s'%str(e))
        self._quietTimeEnabled.value = e
        self.session.commit()
        if self._quietTimeEnabled_changed is not None:
            self._quietTimeEnabled_changed()
    @piccoloChanged
    def callback_quietTimeEnabled(self,cb):
        self._quietTimeEnabled_changed = cb
    @property
    def quietTimeEnabled(self):
        return self.get_quietTimeEnabled()
        
    @piccoloGET
    def get_quietStart(self):
        return self.quietStart.strftime("%H:%M:%S%z")
    @piccoloPUT
    def set_quietStart(self,t):
        self._quietStart.time = self._parseTime(t)
        self.session.commit()
        if self._quietStart_changed is not None:
            self._quietStart_changed()
    @piccoloChanged
    def callback_quietStart(self,cb):
        self._quietStart_changed = cb
    @property
    def quietStart(self):
        qs = self._quietStart.time
        if qs is not None:
            return qs.replace(tzinfo=pytz.utc)

    @piccoloGET
    def get_quietEnd(self):
        return self.quietEnd.strftime("%H:%M:%S%z")
    @piccoloPUT
    def set_quietEnd(self,t):
        self._quietEnd.time = self._parseTime(t)
        self.session.commit()
        if self._quietEnd_changed is not None:
            self._quietEnd_changed()
    @piccoloChanged
    def callback_quietEnd(self,cb):
        self._quietEnd_changed = cb
    @property
    def quietEnd(self):
        qe = self._quietEnd.time
        if qe is not None:
            return qe.replace(tzinfo=pytz.utc)

    @piccoloGET
    def get_jobs(self):
        jobs = []
        for job in self.session.query(PiccoloScheduledJob):
            jobs.append(job.tolist())
        return jobs
    @piccoloChanged
    def callback_jobs(self,cb):
        self._jobs_changed = cb

    @property
    def inQuietTime(self):
        inQuietTime = False
        if self.quietTimeEnabled:
            now = self.now()
            qs = datetime.datetime.combine(now.date(),self.quietStart)
            qe = datetime.datetime.combine(now.date(),self.quietEnd)
            if qs > qe:
                # add a day to account for day boundary
                qe = qe + datetime.timedelta(1)
            if qs < now < qe:
                inQuietTime = True
        return inQuietTime
        
    def add(self,start_time,job,interval=None,end_time=None):
        """add a new job

        :param start_time: the time at which the job should run
        :type start_time: datetime.datetime
        :param job: object returned when scheduled job is run
        :param interval: repeated schedule job if interval is not set to None
        :type interval: datetime.timedelta
        :param end_time: the time after which the job is no longer scheduled
        :type end_time: datetime.datetime or None
        """
        now = self.now()

        if not isinstance(start_time, datetime.datetime):
            start_time = parser.parse(start_time)
        if not (end_time is None or isinstance(end_time, datetime.datetime)):
            end_time = parser.parse(end_time)
        if not (interval is None or isinstance(interval,datetime.timedelta)):
            interval = datetime.timedelta(seconds=float(interval))
        
        if interval is None and start_time < now:
            return
        if end_time is not None and  end_time < now:
            return
            
        new_job = PiccoloScheduledJob(job=job,
                                      start_time=start_time,
                                      interval=interval,
                                      end_time=end_time)
        self.session.add(new_job)
        self.session.commit()
        self.log.info('scheduled job {}'.format(new_job.id))
        if self._jobs_changed is not None:
            self._jobs_changed()
        return new_job

    @property
    def session(self):
        return self._session
    
    @property
    def runable_jobs(self):
        if self.inQuietTime:
            if not self._loggedQuietTime:
                self.log.info("quiet time started, not scheduling any jobs")
                self._loggedQuietTime = True
            return []
        else:
            if self._loggedQuietTime:
                self.log.info("quiet time stopped, scheduling jobs again")
                self._loggedQuietTime = False
        
            now = self.now()
            for job in self.session.query(PiccoloScheduledJob).filter(PiccoloScheduledJob.start_time < now):
                if not job.suspended:
                    self.log.info("running scheduled job {0}".format(job.id))
                    yield job
                if job.interval is not None:
                    n = int((now-job.start_time).total_seconds()//job.interval.total_seconds()+1)
                    if n > 1:
                        self.log.info("job {0}: fast forwarding {1} times".format(job.id,n))
                    job.start_time += n*job.interval
                if job.interval is None or (job.end_time is not None and job.start_time > job.end_time):
                    self.log.info("job {0}: has expired".format(job.id))
                    self.session.delete(job)
                    if self._jobs_changed is not None:
                        self._jobs_changed()
            self.session.commit()



        
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

    
    ps.set_quietStart(qs.timetz())
    ps.set_quietEnd(qe.timetz())

    ps.set_quietTimeEnabled(True)

    for i in range(0,100):
        for job in ps.runable_jobs:
            print (job.id, job.start_time, job.job)
        time.sleep(1)
        if i==27:
            task2.suspend()
        if i==41:
            task2.unsuspend()
        print (i)
