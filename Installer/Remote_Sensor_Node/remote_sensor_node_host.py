"""Transport installer-owned host preparation over SSH; no hardware recipes here."""

import asyncio
from dataclasses import replace
from pathlib import Path
import shlex
import tarfile
import tempfile
from typing import Any

from remote_sensor_node_operations import create_remote_stage, run_remote
from remote_sensor_node_options import DeployOptions
from remote_sensor_node_privilege import RemoteEnvironment, inspect_remote_environment
from remote_sensor_node_scp import scp_with_progress
from remote_sensor_node_stream import stream_root_command


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class HostPreparationError(RuntimeError):
    """Host preparation failed before deployment could begin."""


async def prepare_remote_host(
    asyncssh: Any, connection: Any, options: DeployOptions, destination: str,
) -> RemoteEnvironment:
    stage = None
    try:
        environment = await inspect_remote_environment(connection, destination)
        with tempfile.TemporaryDirectory(prefix="fissure-host.") as name:
            archive = Path(name) / "host-support.tar"
            await asyncio.to_thread(create_installer_archive, archive)
            stage = await create_remote_stage(connection)
            await scp_with_progress(asyncssh, str(archive), (connection, f"{stage}/installer.tar"))
            await run_remote(connection, shlex.join([
                "tar", "-xf", f"{stage}/installer.tar", "-C", stage,
                "--no-same-owner", "--no-same-permissions",
            ]))
            await stream_root_command(
                connection, host_command(stage, environment.user, options), environment.privilege,
            )
        result = await run_remote(connection, "command -v apptainer")
        apptainer = result.stdout.strip()
        if not apptainer:
            raise HostPreparationError("Installer did not provide Apptainer")
        return replace(environment, apptainer=apptainer)
    except Exception as exc:
        raise HostPreparationError(f"Remote host preparation failed: {exc}") from exc
    finally:
        if stage:
            # Cleanup errors must not hide the original installation failure.
            try:
                await run_remote(connection, shlex.join(["rm", "-rf", "--", stage]), check=False)
            except Exception as exc:
                print(f"[!] Could not remove host staging directory {stage}: {exc}")


def host_command(stage: str, user: str, options: DeployOptions) -> list[str]:
    command = ["bash", f"{stage}/Installer/Host/prepare_host.sh",
               f"--user={user}", f"--source-root={stage}",
               f"--hardware={','.join(options.hardware) or 'none'}"]
    if options.skip_host_prep:
        command.append("--check-only")
    if not options.install_apptainer:
        command.append("--no-install-apptainer")
    return command


def create_installer_archive(output: Path) -> None:
    """Stage only installer code and its declared asset, never runtime secrets."""
    manifest = REPOSITORY_ROOT / "Installer/Host/remote_files.txt"
    paths = [REPOSITORY_ROOT / name for name in manifest.read_text().splitlines() if name]
    with tarfile.open(output, "w") as archive:
        for path in paths:
            if (not path.resolve().is_relative_to(REPOSITORY_ROOT)
                    or path.is_symlink() or not path.is_file()):
                raise HostPreparationError(f"Installer asset is not a regular file: {path}")
            archive.add(path, arcname=str(path.relative_to(REPOSITORY_ROOT)), recursive=False)
