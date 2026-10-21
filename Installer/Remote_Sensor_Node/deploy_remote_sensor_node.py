#!/usr/bin/env python3
"""Build, deploy, and maintain a FISSURE Sensor Node with Apptainer and SSH.

Usage:
  deploy_remote_sensor_node.py --build [options]
  deploy_remote_sensor_node.py <destination> --deploy [options]
  deploy_remote_sensor_node.py --target=<destination> --deploy [options]
  deploy_remote_sensor_node.py <destination> [options]
  deploy_remote_sensor_node.py --target=<destination> [options]
  deploy_remote_sensor_node.py (-h | --help)

Options:
  -h --help                  Show this help.
  --target=<destination>     Legacy [user@]IP form (default user: root).
  --build                    Build the Sensor Node SIF locally without SSH.
  --deploy                   Deploy an existing SIF without building one.
  --prepare-host             Prepare host support without deploying a SIF.
  --hardware=<list>          Host support: uhd,usrp-x300,hackrf,rtlsdr,wifi,meshtastic.
  --host-support=<directory>  Offline host-support bundle; implies --offline.
  --offline                  Never download host prerequisites from the internet.
  --skip-host-prep           Validate existing prerequisites without changing them.
  -i <path> --identity=<path>  SSH private key; omit to enter a password.
  --config=<path>            Values for rendered YAML (default: installed YAML).
  --hiprfisr-address=<host>  HIPRFISR endpoint; overrides config and SSH default.
  --certificates=<path>      Certificate root (default: installed certificates).
  --image=<path>             Existing SIF to deploy instead of building.
  --output-image=<path>      Build output and default SIF used by --deploy.
  --source=<path>            FISSURE source tree (default: repository root).
  --build-with-sudo          Build with sudo instead of Apptainer fakeroot.
  --no-install-apptainer     Do not install missing local or remote Apptainer.
  --remote-dir=<path>        Installation root [default: /opt/fissure-sensor-node].
  --service-name=<name>      systemd unit name [default: fissure-sensor-node].
  --health-timeout=<seconds>  Startup and diagnostic timeout [default: 180].
  --health-only              Check without changing the deployment.
  --update-config=<path>     Replace the installed config and restart the service.
  --update-image=<path>      Replace the installed SIF and restart the service.
  --restart                  Restart the installed service without other changes.
  --clear-data=<kind>        Clear logs, artifacts, or recordings and restart.
  --sync-plugins=<path>      Add or update plugins without deleting remote-only files.
  --sync-source=<path>       Add or update host source without deleting remote-only files.
  --uninstall                Remove the remote service and deployment files.
"""
import asyncio
import importlib
from pathlib import Path
import sys
from typing import Any, Sequence

from remote_sensor_node_actions import deploy, run_build_action
from remote_sensor_node_config import ConfigPreparationError
from remote_sensor_node_health import HealthCheckError
from remote_sensor_node_host import HostPreparationError
from remote_sensor_node_local_apptainer import LocalApptainerError
from remote_sensor_node_operations import RemoteOperationError
from remote_sensor_node_options import (
    DeployOptions, DeploymentError, options_from_arguments, validate_options,
)
from remote_sensor_node_plugin_sync import PluginSyncError
from remote_sensor_node_privilege import PrivilegeError
from remote_sensor_node_source_sync import SourceSyncError
from remote_sensor_node_templates import TemplateRenderError

INSTALLER_DIR = Path(__file__).resolve().parent
REPO_ROOT = INSTALLER_DIR.parent.parent


def main(argv: Sequence[str] | None = None) -> int:
    try:
        options = parse_options(argv)
        validate_options(options)
        if options.build_image:
            asyncio.run(run_build_action(options))
            return 0
        asyncssh = load_module("asyncssh")
        asyncio.run(deploy(options, asyncssh))
        return 0
    except (
        HostPreparationError,
        ConfigPreparationError,
        DeploymentError,
        LocalApptainerError,
        PrivilegeError,
        TemplateRenderError,
        HealthCheckError,
        RemoteOperationError,
        PluginSyncError,
        SourceSyncError,
    ) as exc:
        print(f"[!] {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n[!] Operation interrupted", file=sys.stderr)
        return 130



def parse_options(argv: Sequence[str] | None = None) -> DeployOptions:
    docopt = load_module("docopt").docopt
    args = docopt(__doc__, argv=list(argv) if argv is not None else None)
    return options_from_arguments(args, REPO_ROOT)



def load_module(name: str) -> Any:
    try:
        return importlib.import_module(name)
    except ImportError as exc:
        raise DeploymentError(
            f"{name} is required. Install dependencies with: "
            "python3 -m pip install -r "
            "Installer/Remote_Sensor_Node/requirements-node-deploy.txt"
        ) from exc



if __name__ == "__main__":
    raise SystemExit(main())
