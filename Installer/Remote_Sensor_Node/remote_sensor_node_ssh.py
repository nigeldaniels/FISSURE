"""SSH connection and read-only preflight shared by deployment actions."""

import getpass
from typing import Any
import warnings

from remote_sensor_node_options import DeployOptions, DeploymentError, HostSpec
from remote_sensor_node_privilege import (
    PrivilegeError, RemoteEnvironment, prepare_remote_environment,
)


def prompt_for_ssh_password(options: DeployOptions) -> str | None:
    if options.identity_file:
        return None

    target = require_target(options)
    username = f"{target.username}@" if target.username else ""
    prompt = f"SSH password for {username}{target.hostname}: "
    try:
        # getpass otherwise falls back to echoed stdin when no secure terminal exists.
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            password = getpass.getpass(prompt)
    except (EOFError, OSError, getpass.GetPassWarning) as exc:
        raise DeploymentError(
            "Unable to read an SSH password securely; use -i with a private key"
        ) from exc
    if not password:
        raise DeploymentError("SSH password cannot be empty; use -i with a private key")
    return password



async def connect(
    asyncssh: Any, options: DeployOptions, password: str | None
) -> Any:
    target = require_target(options)
    kwargs: dict[str, Any] = {"keepalive_interval": 30}
    if target.username:
        kwargs["username"] = target.username
    if options.identity_file:
        kwargs["client_keys"] = [str(options.identity_file)]
    elif password:
        kwargs.update(client_keys=None, password=password)
    else:
        raise DeploymentError("SSH password is required when -i is not specified")
    try:
        return await asyncssh.connect(target.hostname, **kwargs)
    except (OSError, asyncssh.Error) as exc:
        raise DeploymentError(f"SSH connection failed: {exc}") from exc



def require_target(options: DeployOptions) -> HostSpec:
    if not options.target:
        raise DeploymentError("An SSH destination is required for this action")
    return options.target



async def preflight(
    connection: Any,
    destination: str,
) -> RemoteEnvironment:
    try:
        return await prepare_remote_environment(
            connection,
            destination,
        )
    except PrivilegeError as exc:
        raise DeploymentError(str(exc)) from exc
