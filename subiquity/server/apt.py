# Copyright 2021 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import datetime
import os
import shutil
import tempfile

from curtin.util import write_file

import yaml

from subiquitycore.lsb_release import lsb_release

from subiquity.server.curtin import run_curtin_command


class AptConfigurer:

    def __init__(self, app, target):
        self.app = app
        self.target = target
        self._mounts = []
        self._tdirs = []

    def tdir(self):
        d = tempfile.mkdtemp()
        self._tdirs.append(d)
        return d

    def tpath(self, *args):
        return os.path.join(self.target, *args)

    async def mount(self, device, mountpoint, options=None, type=None):
        opts = []
        if options is not None:
            opts.extend(['-o', options])
        if type is not None:
            opts.extend(['-t', type])
        await self.app.command_runner.run(
            ['mount'] + opts + [device, mountpoint])
        self._mounts.append(mountpoint)

    async def unmount(self, mountpoint):
        await self.app.command_runner.run(['umount', mountpoint])

    async def setup_overlay(self, dir):
        tdir = self.tdir()
        w = f'{tdir}/work'
        u = f'{tdir}/upper'
        for d in w, u:
            os.mkdir(d)
        await self.mount(
            'overlay', dir, type='overlay',
            options=f'lowerdir={dir},upperdir={u},workdir={w}')

    async def configure(self, context):
        # Configure apt so that installs from the pool on the cdrom are
        # preferred during installation but not in the installed system.
        #
        # This has a few steps.
        #
        # 1. As the remaining steps mean that any changes to apt configuration
        #    are do not persist into the installed system, we get curtin to
        #    configure apt a bit earlier than it would by default.
        #
        # 2. Bind-mount the cdrom into the installed system as /cdrom.
        #
        # 3. Set up an overlay over /target/etc/apt. This means that any
        #    changes we make will not persist into the installed system and we
        #    do not have to worry about cleaning up after ourselves.
        #
        # 4. Configure apt in /target to look at the pool on the cdrom.  This
        #    has two subcases:
        #
        #     a. if we expect the network to be working, this basically means
        #        prepending
        #        "deb file:///run/cdrom $(lsb_release -sc) main restricted"
        #        to the sources.list file.
        #
        #     b. if the network is not expected to be working, we replace the
        #        sources.list with a file just referencing the cdrom.
        #
        # 5. If the network is not expected to be working, we also set up an
        #    overlay over /target/var/lib/apt/lists (if the network is working,
        #    we'll run "apt update" after the /target/etc/apt overlay has been
        #    cleared).

        config = {
            'apt': self.app.base_model.mirror.config,
            }
        config_location = os.path.join(
            self.app.root, 'var/log/installer/subiquity-curtin-apt.conf')

        with open(config_location, 'w') as conf:
            datestr = '# Autogenerated by Subiquity: {} UTC\n'.format(
                str(datetime.datetime.utcnow()))
            conf.write(datestr)
            conf.write(yaml.dump(config))

        self.app.note_data_for_apport("CurtinAptConfig", config_location)

        await run_curtin_command(
            self.app, context, 'apt-config', '-t', self.tpath(),
            config=config_location)

        await self.setup_overlay(self.tpath('etc/apt'))

        os.mkdir(self.tpath('cdrom'))
        await self.mount('/cdrom', self.tpath('cdrom'), options='bind')

        if self.app.base_model.network.has_network:
            os.rename(
                self.tpath('etc/apt/sources.list'),
                self.tpath('etc/apt/sources.list.d/original.list'))
        else:
            proxy_path = self.tpath('etc/apt/apt.conf.d/90curtin-aptproxy')
            if os.path.exists(proxy_path):
                os.unlink(proxy_path)
            await self.setup_overlay(self.tpath('var/lib/apt/lists'))

        codename = lsb_release()['codename']

        write_file(
            self.tpath('etc/apt/sources.list'),
            f'deb [check-date=no] file:///cdrom {codename} main restricted\n',
            )

        await run_curtin_command(
            self.app, context, "in-target", "-t", self.tpath(),
            "--", "apt-get", "update")

    async def deconfigure(self, context):
        for m in reversed(self._mounts):
            await self.unmount(m)
        for d in self._tdirs:
            shutil.rmtree(d)
        if not self.app.opts.dry_run:
            os.rmdir(self.tpath('cdrom'))
        if self.app.base_model.network.has_network:
            await run_curtin_command(
                self.app, context, "in-target", "-t", self.tpath(),
                "--", "apt-get", "update")
