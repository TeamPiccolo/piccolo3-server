# Copyright 2018- The Piccolo Team
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

from setuptools import setup, find_packages

setup(
    name = "piccolo3-server",
    namespace_packages = ['piccolo3'],
    packages = find_packages(),
    use_scm_version=True,
    setup_requires=['setuptools_scm'],
    include_package_data = True,
    install_requires = [
        'psutil',
        'aiocoap',
        'pytz',
    ],
    entry_points={
    },

    # metadata for upload to PyPI
    author = "Magnus Hagdorn, Alasdair MacArthur, Iain Robinson",
    description = "Part of the piccolo3 system. This package provides the piccolo3 server",
    license = "GPL",
    url = "https://bitbucket.org/teampiccolo/piccolo3-server",
)
