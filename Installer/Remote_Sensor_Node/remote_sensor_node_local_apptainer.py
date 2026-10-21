"""Install the local Apptainer prerequisite before remote deployment."""

import asyncio
import os
import shutil
from pathlib import Path


class LocalApptainerError(RuntimeError):
    """Raised when the local Apptainer prerequisite cannot be prepared."""


async def ensure_local_apptainer(allow_install: bool) -> str:
    """Return the local binary, installing it when permitted and necessary."""
    apptainer = shutil.which("apptainer")
    if apptainer:
        return apptainer
    if not allow_install:
        raise LocalApptainerError("Apptainer is not installed locally")

    command = ["bash", str(Path(__file__).resolve().parent.parent / "install_apptainer_package.sh")]
    if os.geteuid() != 0:
        sudo = shutil.which("sudo")
        if not sudo:
            raise LocalApptainerError(
                "sudo is required to install Apptainer locally"
            )
        command.insert(0, sudo)

    print("[*] Apptainer is missing locally; installing it from the official PPA")
    process = await asyncio.create_subprocess_exec(*command)
    if await process.wait():
        raise LocalApptainerError("Local Apptainer installation failed")

    apptainer = shutil.which("apptainer")
    if not apptainer:
        raise LocalApptainerError(
            "Local Apptainer installation did not provide a binary"
        )
    return apptainer
