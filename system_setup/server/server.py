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

from system_setup.common.wsl_utils import is_reconfigure
from subiquity.server.server import SubiquityServer
from system_setup.models.system_setup import SystemSetupModel
from subiquity.models.subiquity import ModelNames

import logging
import yaml
import os

log = logging.getLogger('system_setup.server.server')

INSTALL_MODEL_NAMES = ModelNames({
        "locale",
        "wslconfbase",
    },
    wsl_setup={
        "identity",
    },
    wsl_configuration={
        "wslconfadvanced",
    })

POSTINSTALL_MODEL_NAMES = ModelNames(set())


class SystemSetupServer(SubiquityServer):

    from system_setup.server import controllers as controllers_mod
    controllers = [
        "Early",
        "Reporting",
        "Error",
        "Locale",
        "WSLIdentity",
        "WSLConfigurationBase",
        "WSLConfigurationAdvanced",
        "Configure",
        "Late",
        "SetupShutdown",
    ]

    supported_variants = ["wsl_setup", "wsl_configuration"]

    def __init__(self, opts, block_log_dir):
        super().__init__(opts, block_log_dir)
        self.echo_syslog_id = ""
        self.event_syslog_id = ""
        self.log_syslog_id = ""
        if is_reconfigure(opts.dry_run):
            self.set_source_variant("wsl_configuration")

    def make_model(self):
        root = '/'
        prefillInfo = None
        if self.opts.dry_run:
            root = os.path.abspath('.subiquity')
        if self.opts.prefill:
            with open(self.opts.prefill, 'r') as stream:
                try:
                    prefillInfo = yaml.safe_load(stream)
                except yaml.YAMLError as exc:
                    log.error('Exception while parsing prefill file: {}.'
                              ' Ignoring file.'.format(exc))
                    prefillInfo = None
        return SystemSetupModel(root, self.hub, INSTALL_MODEL_NAMES,
                                POSTINSTALL_MODEL_NAMES, prefillInfo)

    # We don’t have cloudinit in system_setup.
    async def wait_for_cloudinit(self):
        self.cloud_init_ok = True
        return
