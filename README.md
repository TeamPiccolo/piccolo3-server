# Piccolo3 Server

This is the server component of the piccolo3 spectral system.

The piccolo3 server is multithreaded python3 application that controls 
multiple [Ocean Optics](http://www.oceanoptics.com/) spectrometers using the 
[seabreeze](https://pypi.org/project/seabreeze/) package. The piccolo3 server
itself is controlled via the 
[constrained application protocol (CoAP)](http://www.oceanoptics.com/).
It also uses the python3 
[asyncio](https://docs.python.org/3/library/asyncio.html) 
framework for co-routines.

The piccolo3 server is designed to run on a raspberry pi system. It makes use 
of the GPIO system to control the shutters.

## Installation

On an up-to-date Raspberry Pi OS bullseye system install the following packages
```
apt install python3-numpy python3-psutil python3-configobj python3-daemon \
            python3-tz python3-gpiozero python3-dateutil python3-lockfile \
            python3-bitarray python3-scipy python3-sqlalchemy python3-usb \
            python3-virtualenv
```

Install the seabreeze package:
```
sudo apt install build-essential libusb-dev
sudo pip install seabreeze
sudo seabreeze_os_setup
```
The last steps copies the oceanoptics udev rule os_support/10-oceanoptics.rule from the [seabreeze package](https://github.com/ap--/python-seabreeze.git) to `/etc/udev/rules.d`.

Create a virtual environment with access to system packages
```
python3 -m venv --system-site-packages /path/to/venv
```
and activate it
```
. /path/to/venv/bin/activate
```

Install the [piccolo3-common](https://github.com/TeamPiccolo/piccolo3-common)
package and then the server package.

## Setup

The piccolo3 server is configured using two config files:
1. the server configuration typically stored in `/etc/piccolo.cfg`:
```
[coap]
# The server address to listen on, can be an IP address or resolvable host name. By default listen on all interfaces
address = ::
# The port to listen on. By default use the CoAP port 5683
port = 5683

[daemon]
# run piccolo server as daemon
daemon = False
# name of PID file
pid_file = /var/run/piccolo.pid

# configure the data directory
[datadir]
mount = True
datadir = piccolo3_data
device = /dev/sda1

[logging]
debug = False
```
2. the instrument specific configuration file which is stored in the `datadir` 
configured in the server configuration file. Have a long at the example file
[pdata/piccolo.config](pdata/piccolo.config).

## Running the Server

Once configured, you can run the server using
```
piccolo3-server -s /etc/piccolo.cfg
```

Have a look at [coap.md](coap.md) for instructions on how to communicate with
the server using the CoAP protocol. Alternatively, install the 
[piccolo3-client](https://github.com/TeamPiccolo/piccolo3-client) to 
communicate with the piccolo3 server using python. You can also use the
[piccolo3-web](https://github.com/TeamPiccolo/piccolo3-web) web application 
to control the server using a browser.
