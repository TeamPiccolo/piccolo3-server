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

import time
import gpiozero
import os
from piccolo3.common import piccoloLogging
import logging
import signal
import sys

# the pin number used for the reboot button
REBOOT_BUTTON_PIN = 10
# time in seconds after which system is powered off
POWER_DOWN = 5

log = logging.getLogger("piccolo.reboot")

def stop_piccolo(signum, frame):
    log.info ('quit')
    sys.exit(1)
for s in [signal.SIGINT,signal.SIGTERM]:
    signal.signal(s,stop_piccolo)

def action(b):
    ts = time.time()
    b.wait_for_release(timeout=POWER_DOWN)
    duration = time.time()-ts
    if duration>POWER_DOWN:
        log.info ('shutdown')
        os.system("sudo shutdown -h now")
    else:
        log.info ('reboot')
        os.system("sudo shutdown -r now")

def main():
    piccoloLogging()
    
    log.info('waiting for reboot button')
    button = gpiozero.Button(REBOOT_BUTTON_PIN)
    button.when_held = action
    while True:
        time.sleep(0.1)


if __name__ == '__main__':
    main()
