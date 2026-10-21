# FISSURE Remote Sensor Node Deployment

This directory contains the complete Apptainer-based deployment workflow for a
remote FISSURE Sensor Node. Run all commands below from the FISSURE repository
root.

The utility builds a Sensor Node SIF locally or deploys an existing SIF over
SSH. Deployment renders configuration with Jinja2, stages the installed
certificates, transfers the payload, and installs a systemd service on the
target.

## Quick start

Install the deployment-only Python dependencies:

```bash
python3 -m pip install -r \
  Installer/Remote_Sensor_Node/requirements-node-deploy.txt
```

Build the Sensor Node SIF without connecting to a remote host:

```bash
Installer/Remote_Sensor_Node/deploy_remote_sensor_node.py --build
```

Deploy that SIF to a target:

```bash
Installer/Remote_Sensor_Node/deploy_remote_sensor_node.py \
  192.0.2.20 --deploy
```

An IP-only target uses the remote `root` account. Without `-i`, the deployer
securely prompts for the SSH password.

To use a non-root account and an SSH key:

```bash
Installer/Remote_Sensor_Node/deploy_remote_sensor_node.py \
  fissure@192.0.2.20 --deploy -i ~/.ssh/fissure-node
```

The deployer tries passwordless `sudo` after connecting as a non-root user. If
that is unavailable, it securely prompts for the sudo password.
During SCP, each file reports its percentage and transferred/total size. The
multi-gigabyte SIF therefore remains visibly active throughout the upload.

## Templates and local inputs

The complete deployment configuration is visible under `templates/`:

- `sensor-node.yml.j2` renders the remote Sensor Node YAML.
- `fissure-sensor-node.service.j2` renders the installed systemd unit.
- `remote_sensor_node_apptainer.def.j2` renders the local image definition.

Jinja2 uses strict undefined-variable handling, so an incomplete template
context stops deployment instead of emitting a partially configured file.
By default, inputs come from the current FISSURE installation:

- `YAML/Sensor_Node_Config/default.yaml`
- `certificates/clients/client_0.key_secret`
- `certificates/server/server.key`
- `Installer/Remote_Sensor_Node/build/fissure-sensor-node.sif`

`--build` installs local Apptainer when permitted and writes the SIF to
`--output-image`. `--deploy` uses that output by default, or `--image` to select
another existing SIF. Deployment never starts a local image build. Use
`--no-install-apptainer` to prohibit automatic local or remote Apptainer
installation for the selected action.
Automatic installation uses the same `Installer/install_apptainer_package.sh`
path as the standard FISSURE Apptainer installer.

Rendered configuration and node certificates are transferred separately and
bind-mounted read-only. They are never baked into the SIF. Rendering preserves
the installed Sensor Node values. Use `--hiprfisr-address` when the FISSURE
communications route differs from the SSH route. Otherwise, a loopback
HIPRFISR address is replaced with the local endpoint of the established SSH
connection. Rendering performs no host discovery and does not change the
installed source YAML. Certificates remain ordinary external files because
secrets must never be placed in templates.

## Host preparation

Deployment prepares Apptainer when needed. Hardware preparation is explicit;
no hardware flag means no additional radio setup. A prepared runtime must have
Apptainer setuid support, matching the standard FISSURE Apptainer installer.

Prepare a host independently of any image, configuration, or certificates:

```bash
Installer/Remote_Sensor_Node/deploy_remote_sensor_node.py \
  fissure@192.0.2.20 --prepare-host -i ~/.ssh/fissure-node \
  --hardware=uhd,hackrf
```

Or prepare hardware as part of deploying an existing SIF:

```bash
Installer/Remote_Sensor_Node/deploy_remote_sensor_node.py \
  fissure@192.0.2.20 --deploy -i ~/.ssh/fissure-node \
  --hardware=uhd --hiprfisr-address=192.0.2.10
```

| Selection | Existing installer setup reused |
| --- | --- |
| `uhd` | UHD tools, USB rules, user permissions, and FPGA images; includes B2xx support |
| `usrp-x300` | UHD preparation plus X300/X310 socket-buffer tuning |
| `hackrf` | HackRF packages and FISSURE udev rules |
| `rtlsdr` | RTL-SDR USB access and DVB driver blacklist |
| `wifi` | The existing rtl8812au DKMS driver recipe and running-kernel headers |
| `meshtastic` | Meshtastic Python support and serial-device access |
| `none` | Apptainer only; also the default |

Selections are comma-separated and never prompt again. UHD is prepared once
when both `uhd` and `usrp-x300` are selected. Required package, firmware, and
driver failures stop preparation; a disconnected radio can be reported as a
diagnostic without failing installation. Reconnect or reboot notices require
operator action; preparation does not reboot the host. The existing X300 buffer
adjustment applies to the running kernel and must be reapplied after reboot.

For an already prepared host, deploy with `--skip-host-prep` to check existing
prerequisites without installing packages or configuring hardware. It cannot
be combined with hardware selections or a support bundle. Maintenance actions
such as `--restart` and `--sync-source` never prepare hardware.
`--no-install-apptainer` prohibits Apptainer installation from either source,
while allowing explicitly selected online hardware preparation.

The same host preparation can run directly on a machine, without SSH:

```bash
Installer/Host/prepare_host.sh --hardware=uhd --user=fissure
```

This requires a pre-existing target account and invokes sudo when needed.
The existing local `Installer/install_apptainer.sh` also accepts
`--hardware=uhd,hackrf` or `--hardware=none` to override its hardware defaults.
Its other legacy defaults, including optional services and image building,
remain in effect.

### Offline Apptainer support

On a connected Ubuntu 24.04 machine or VM with the **same architecture** as the
target, prepare a new bundle directory:

```bash
Installer/Host/prepare_support_bundle.sh --output=/path/to/new-host-support
```

The producer needs `apt-get`, `curl`, `gpg`, `dpkg-deb`, `dpkg-scanpackages`
(from `dpkg-dev`), and the Ubuntu archive keyring. It uses isolated package
indexes and an empty package-status database so dependencies already installed
on the producer are still included. It does not install Apptainer on the
producer or change its configured APT sources. Existing output directories are
never replaced.

Transfer and consume the bundle over the management connection:

```bash
Installer/Remote_Sensor_Node/deploy_remote_sensor_node.py \
  fissure@192.0.2.20 --prepare-host -i ~/.ssh/fissure-node \
  --host-support=/path/to/new-host-support
```

Use the same `--host-support` option with `--deploy` and an existing, matching
SIF to prepare and deploy in one operation. The bundle and SIF remain separate
files. The target needs working SSH, Bash, APT/dpkg, systemd, and udev, as on a
normal Ubuntu installation. No Dashboard or HIPRFISR needs to be running.

`--host-support` implies `--offline`. Without a bundle, `--offline` requires
compatible Apptainer support to be present already. Offline mode has no
internet fallback. OS/architecture mismatch, corruption, missing packages, or
unsupported selections fail explicitly. V1 supports Ubuntu 24.04 `amd64` and
`arm64`; offline radio selections other than `none` are rejected. Offline SIF
building and cross-architecture bundle production are not included.

The producer verifies signed Ubuntu and Apptainer package indexes. Bundle
checksums detect transfer corruption; the consumer trusts the operator-supplied
bundle. It configures a temporary, local-file-only APT source without inheriting
host repositories or APT hooks, simulates dependency resolution, fills a private
cache from that source, and installs with downloading disabled.

See [implementation boundaries and the verification checklist](../../docs/REMOTE_HOST_PREPARATION.md)
for completed checks and the remaining Ubuntu/ARM validation work.

## Mutable runtime state

The SIF supplies runtime dependencies and the initial application source. Data
that changes outside the image is stored under the host's `state/` directory
and bind-mounted into the container:

- `state/source/fissure` for Python application source and runtime overrides
- `state/runtime/plugins` for installed and transferred plugins
- `state/runtime/flow-graphs` for independently updated flow graphs
- `state/runtime/artifacts*` for node and operation artifacts
- `state/runtime/archive` and `state/runtime/iq-recordings` for recordings
- `state/runtime/sensor-node` for autorun, playback, import/export, and files
- `state/logs` and `state/runtime/plugin-logs` for core and plugin logs
- `state/home` for the persistent sensor-node UUID and user runtime files

Initial source, plugins, flow graphs, archive data, and sensor-node runtime
files are seeded from the SIF only when their host directories are empty.
Existing host content is preserved across full deployments and SIF updates.
Deployments made with the former persistent overlay are migrated into these
directories when they are next fully deployed; the old overlay is then no
longer mounted.

Apptainer uses an ephemeral writable tmpfs for incidental process writes. No
general persistent overlay is created for new deployments.

## Operations

Check an existing deployment without changing it:

```bash
Installer/Remote_Sensor_Node/deploy_remote_sensor_node.py \
    192.0.2.20 --health-only
```

Replace only the active Sensor Node configuration and restart the service:

```bash
Installer/Remote_Sensor_Node/deploy_remote_sensor_node.py \
    192.0.2.20 --update-config=/path/to/sensor-node.yaml
```

This uses the normal configuration rendering and SSH privilege paths. It
atomically replaces `current/default.yaml`, restarts the existing service, and
checks startup without rebuilding or transferring the SIF.

Restart the installed service without changing its files:

```bash
Installer/Remote_Sensor_Node/deploy_remote_sensor_node.py \
    192.0.2.20 --restart
```

The restart action performs the same startup-only validation and does not
require a running Dashboard or HIPRFISR.

Replace only the active SIF and restart the service:

```bash
Installer/Remote_Sensor_Node/deploy_remote_sensor_node.py \
    192.0.2.20 --update-image=/path/to/fissure-sensor-node.sif
```

The image update uses SCP progress reporting and atomically replaces the active
SIF. It does not build an image, create another release, or change the external
source, configuration, certificates, plugins, artifacts, recordings, logs, or
node identity.

Clear one category of mutable host data and restart the service:

```bash
Installer/Remote_Sensor_Node/deploy_remote_sensor_node.py \
    192.0.2.20 --clear-data=logs
```

The operation stops the service, removes the contents of the selected category,
and starts the service again. It preserves the directories, their ownership,
and all other mutable data.

- `logs`: core logs and plugin logs
- `artifacts`: general, node, and system artifact directories
- `recordings`: archive, IQ recording, archive-replay, and Sensor Node recording
  directories

`logs` does not clear the host's systemd journal.

Synchronize local plugins without removing plugins that exist only on the node:

```bash
Installer/Remote_Sensor_Node/deploy_remote_sensor_node.py \
    192.0.2.20 --sync-plugins=/path/to/Plugins
```

The sync adds new files and overwrites matching files in the host plugin
directory. It ignores local Python caches and repository metadata, clears stale
remote Python caches, restarts the service, and performs a startup check.

Synchronize a local FISSURE source tree without removing files that exist only
on the node:

```bash
Installer/Remote_Sensor_Node/deploy_remote_sensor_node.py \
    192.0.2.20 --sync-source=/path/to/FISSURE
```

The source sync copies the local `fissure/` application tree while excluding
caches, secrets, symbolic links, and Sensor Node directories already managed
as separate mutable state. It merges that tree into `state/source/fissure`,
installs the source-aware service unit when needed, restarts the service, and
performs a startup check. Build-time content such as `Custom_Blocks` remains
supplied by the SIF. Later SIF updates preserve the synchronized Python source.

Remove the remote service and deployment state:

```bash
Installer/Remote_Sensor_Node/deploy_remote_sensor_node.py \
  192.0.2.20 --uninstall
```

Uninstall preserves the remote Apptainer package and local cached SIF.

Run the command with `--help` for configuration, image, service, and
health-timeout options.
The default 180-second window covers heavyweight SensorNode imports. Normal
deployment validates systemd state, `MainPID`, and the persistent
`sensor_node_uuid.uuid` without requiring a running Dashboard or HIPRFISR.
The explicit `--health-only` diagnostic additionally requires a fresh matching
heartbeat receipt in the local HIPRFISR event log for IP nodes.

## Safety and lifecycle

Each deployment creates a timestamped remote release. Source, configuration,
certificates, plugins, artifacts, recordings, logs, runtime files, and node
identity remain in explicit host paths outside the SIF. Startup and explicit
diagnostic failures are reported without automatically changing the installed
release.
Service startup rechecks configuration and certificates without recursively
importing heavyweight runtime modules already validated during the image build.

The default remote installation root is `/opt/fissure-sensor-node`.

## Directory contents

| File | Purpose |
| --- | --- |
| `deploy_remote_sensor_node.py` | CLI entrypoint and error reporting |
| `remote_sensor_node_actions.py` | Build, deployment, and maintenance orchestration |
| `remote_sensor_node_host.py` | Transfer installer assets and invoke host preparation |
| `remote_sensor_node_ssh.py` | SSH connection and read-only maintenance preflight |
| `remote_sensor_node_stream.py` | Bounded output streaming and process supervision |
| `remote_sensor_node_config.py` | Remote configuration staging |
| `remote_sensor_node_archive.py` | Filtered directory archives for synchronization |
| `remote_sensor_node_deploy_utilities.py` | Remote lifecycle shell scripts |
| `remote_sensor_node_image_check.py` | Image and runtime prerequisite checks |
| `remote_sensor_node_image.py` | Local image selection and build context |
| `remote_sensor_node_local_apptainer.py` | Local Apptainer installation |
| `remote_sensor_node_options.py` | CLI option parsing, models, and validation |
| `remote_sensor_node_plugin_sync.py` | Plugin archive and synchronization |
| `remote_sensor_node_source_sync.py` | Source archive and synchronization |
| `remote_sensor_node_privilege.py` | Remote account inspection and privilege acquisition |
| `remote_sensor_node_health.py` | Startup and optional heartbeat diagnostics |
| `remote_sensor_node_scp.py` | Interactive and log-friendly SCP progress |
| `remote_sensor_node_templates.py` | Strict Jinja2 rendering boundary |
| `remote_sensor_node_uninstall.py` | Remote uninstall orchestration |
| `requirements-node-deploy.txt` | Deployment-only Python dependencies |
| `templates/` | Sensor YAML, systemd, and Apptainer Jinja2 templates |
