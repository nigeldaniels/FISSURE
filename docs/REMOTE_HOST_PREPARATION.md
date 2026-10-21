# Shared host preparation: implementation and verification

Implementation record: 2026-10-20. Runtime usage is documented in the
[remote deployment README](../Installer/Remote_Sensor_Node/README.md#host-preparation).

## Ownership and entry points

| Boundary | Entry point and responsibility |
| --- | --- |
| Local installation | `Installer/install_apptainer.sh` keeps its legacy defaults and calls focused installer modules |
| Headless host preparation | `Installer/Host/prepare_host.sh` validates selections and invokes shared package and radio routines |
| Offline bundle creation | `Installer/Host/prepare_support_bundle.sh` downloads a native dependency closure into a portable directory |
| Remote orchestration | `Installer/Remote_Sensor_Node/deploy_remote_sensor_node.py` parses options; action modules manage SSH, staging, and lifecycle |
| Image construction | Both builders call `Installer/Apptainer/build_image.sh`; image recipes still invoke the existing installer modes |

The remote utility sends the files declared in `Installer/Host/remote_files.txt`.
It contains no hardware package lists, firmware download instructions, or udev
recipes. Local and remote callers use the same installer-owned hardware code.
Desktop startup, PostgreSQL, IQEngine, TAK, and Xpra recipes were mechanically
extracted to keep the local entry point small; they are not part of the remote
preparation kit.

Data flow:

1. Parse and validate the requested action and hardware selection locally.
2. Inspect the remote account and acquire existing root/sudo privileges.
3. Package the declared installer files and optional support bundle off the
   asyncio event loop; transfer them to a private temporary remote directory.
4. Run the shared host entry point with explicit user, selection, and source
   arguments. Stream stdout/stderr in fixed-size chunks.
5. Validate Apptainer availability and clean staging. A full deployment then
   continues through the existing SIF/configuration/certificate/service path.

For offline preparation, signed Ubuntu/PPA indexes feed a producer with an
empty package-status database. The consumer checks the complete file inventory,
checksums, platform metadata, package architectures, and local index paths. Its
private APT configuration has one `file:` source and no inherited host sources
or hooks. Dependency resolution is simulated before installation, and package
installation uses a private cache with downloading disabled.

## Important invariants and performance

- SensorNode mode remains authoritative for software installed in the SIF.
- No hardware selection means no additional radio preparation. Explicit local
  selections override legacy hardware defaults; other local defaults remain.
- Maintenance actions do not run host preparation. Standalone preparation does
  not require a SIF, certificates, configuration, Dashboard, or HIPRFISR.
- Runtime message formats, node identity storage, certificate selection,
  persistent data paths, and the systemd service template were not changed.
- Offline mode never falls back to online acquisition. An empty bundle argument
  is rejected rather than silently selecting the online path.
- Compatible Apptainer installations are reused. UHD preparation runs once when
  both UHD and X300 are requested; hardware package indexes refresh once per run.
- Archive construction uses disk-backed temporary files and worker threads;
  large package files are streamed into the archive. SSH output is consumed in
  4 KiB chunks, without retaining a growing installation log in memory.
- The supervisor forwards cancellation to its child process group, escalating
  from TERM to KILL. Temporary staging is removed on success, error, or cancellation.
- Sudo secrets travel over stdin, never command arguments or diagnostic logs.
- Bundle publication uses a temporary directory on the destination filesystem
  and does not replace an existing output directory.

## Review sequence

The upstream synchronization is a separate merge. The implementation is split
into these reviewable commits:

1. **Extract shared Apptainer and host preparation routines.** Mechanical
   extraction and common image-build execution, preserving local defaults.
2. **Reuse installer host preparation in remote deployments.** Explicit
   selections, standalone preparation, validation-only deployment, shared
   hardware invocation, and process/transfer lifecycle management.
3. **Add offline Apptainer host-support bundles.** Bundle production, validation,
   transport, and local-only package installation.
4. **Document shared host preparation and verification.** Operator workflows,
   architecture boundaries, this implementation record, and remaining checks.

Each implementation commit includes its relevant focused tests. The extraction
and remote-integration commits were also tested independently in clean snapshots
(4 and 17 tests respectively). No existing PR commits were rewritten.

## Verification completed

Run the focused suite from the repository root:

```bash
python3 -m unittest \
  tests.test_installer_shared \
  tests.test_host_preparation \
  tests.test_host_support_bundle
```

Completed on Ubuntu 24.04 amd64:

- 28 focused tests passed, including actual shared shell dispatch, option
  validation, read-only prerequisite checks, credential handling, failure and
  cancellation cleanup, and a supervised child that ignores TERM.
- Tests built tiny Debian packages and used real APT simulation to verify local
  dependency resolution and failure on a missing dependency. No fixture packages
  were installed.
- Corrupt files, extra files, links, checksum path traversal, architecture
  mismatch, empty bundle arguments, and conflicting actions were rejected.
- The real producer downloaded 77 signed-index-selected packages, approximately
  65 MB, into `/tmp/fissure-apptainer-offline-proof`. It did not install packages
  or modify the workstation's configured APT sources.
- That real bundle passed validation and local-only APT installation simulation.
  A syscall trace of the simulation contained no IPv4 or IPv6 network calls.
- Shell syntax, Python compilation, whitespace checks, and the 500-line source
  limit passed. All eleven mechanically extracted recipes were compared with
  their original command text before introducing shared preparation behavior.

## Pending live verification checklist

These checks have **not** been performed. They require chosen test machines and
fresh approval before deploying or changing live hosts.

- [ ] Clean Ubuntu 24.04 amd64: prepare with root, passwordless sudo, and password
      sudo; confirm the intended service user's permissions.
- [ ] Ubuntu 24.04 ARM64 on a Pi/SBC: create a native bundle, prepare the host,
      and repeat service and selected-radio checks.
- [ ] Disconnect a clean target from the internet and install Apptainer from the
      real bundle. Confirm that required dependencies are present and no
      external package sources are used.
- [ ] Confirm repeated preparation reuses compatible installations and that
      `--skip-host-prep` / `--no-install-apptainer` behave as documented.
- [ ] Exercise the actual selected USB/network radios, including disconnected
      device diagnostics, UHD firmware, udev access, and any required reconnect.
- [ ] For rtl8812au, verify the selected Ubuntu kernel's headers, DKMS build, and
      module load on each intended architecture.
- [ ] Build the real SensorNode SIF and verify both normal fakeroot and explicit
      sudo build paths where supported. Check the local sandbox workflow too.
- [ ] Deploy without Dashboard/HIPRFISR running; verify systemd status, startup,
      restart, reboot, logs, and later connection to the configured endpoint.
- [ ] Exercise image/config/source/plugin updates and confirm preservation of
      node UUID, certificates, recordings, plugins, and logs.
- [ ] Interrupt real SSH transfer and preparation on disposable hosts; verify
      remote process/staging cleanup and document any required package recovery.
- [ ] Exercise the local desktop/optional-service paths, including Xpra, to
      validate the mechanical extraction on an actual installation.

## Limitations and follow-up

The offline proof covers Apptainer on Ubuntu 24.04 amd64/arm64. Radio packages,
other distributions, cross-architecture bundle production, and offline SIF
building remain outside this change. Physical ARM, radio, and systemd behavior
is not established by the automated tests.

APT/driver installation is not transactional. Cancelling installation stops
processes but does not roll back packages or host configuration; standard package
recovery can be necessary after interruption. There is no automatic rollback or
new release-management framework.

The original `/home/shiz/FISSURE` checkout and its uncommitted SIF build-context
and TensorFlow fixes were preserved. Those fixes are not part of this commit
series and should be reviewed separately before the next real image build.
No deployment, push, or publication was performed.

## Changed source files and line counts

Counts below describe this implementation relative to the upstream merge
baseline, excluding upstream-owned changes. The non-source changes are the
installer transfer manifest, the remote deployment README, and this report.

| Source file | Lines |
| --- | ---: |
| `Installer/Apptainer/build_image.sh` | 25 |
| `Installer/Apptainer/build_local.sh` | 60 |
| `Installer/Apptainer/certificates.sh` | 35 |
| `Installer/Apptainer/launcher.sh` | 37 |
| `Installer/Host/apptainer_packages.sh` | 79 |
| `Installer/Host/common.sh` | 37 |
| `Installer/Host/desktop_autostart.sh` | 84 |
| `Installer/Host/hackrf.sh` | 12 |
| `Installer/Host/hardware.sh` | 42 |
| `Installer/Host/iqengine.sh` | 54 |
| `Installer/Host/meshtastic.sh` | 11 |
| `Installer/Host/postgresql.sh` | 41 |
| `Installer/Host/prepare_host.sh` | 60 |
| `Installer/Host/prepare_support_bundle.sh` | 55 |
| `Installer/Host/rtlsdr.sh` | 11 |
| `Installer/Host/support_bundle.sh` | 93 |
| `Installer/Host/takserver.sh` | 159 |
| `Installer/Host/uhd.sh` | 23 |
| `Installer/Host/usrp_x300.sh` | 6 |
| `Installer/Host/wifi.sh` | 18 |
| `Installer/Host/xpra.sh` | 88 |
| `Installer/Remote_Sensor_Node/deploy_remote_sensor_node.py` | 117 |
| `Installer/Remote_Sensor_Node/remote_sensor_node_actions.py` | 330 |
| `Installer/Remote_Sensor_Node/remote_sensor_node_deploy_utilities.py` | 354 |
| `Installer/Remote_Sensor_Node/remote_sensor_node_host.py` | 108 |
| `Installer/Remote_Sensor_Node/remote_sensor_node_image.py` | 83 |
| `Installer/Remote_Sensor_Node/remote_sensor_node_local_apptainer.py` | 40 |
| `Installer/Remote_Sensor_Node/remote_sensor_node_options.py` | 311 |
| `Installer/Remote_Sensor_Node/remote_sensor_node_privilege.py` | 177 |
| `Installer/Remote_Sensor_Node/remote_sensor_node_ssh.py` | 72 |
| `Installer/Remote_Sensor_Node/remote_sensor_node_stream.py` | 65 |
| `Installer/install_apptainer.sh` | 291 |
| `Installer/install_apptainer_package.sh` | 38 |
| `tests/test_host_preparation.py` | 202 |
| `tests/test_host_support_bundle.py` | 176 |
| `tests/test_installer_shared.py` | 71 |
