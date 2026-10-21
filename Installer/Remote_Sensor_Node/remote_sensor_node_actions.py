"""Orchestrate build, deployment, and maintenance using focused services."""

import asyncio
from dataclasses import replace
from pathlib import Path
import shlex
import tempfile
import time
from typing import Any

from remote_sensor_node_config import prepare_remote_config
from remote_sensor_node_deploy_utilities import DeploymentUtilities
from remote_sensor_node_health import wait_for_sensor_node_health
from remote_sensor_node_host import prepare_remote_host
from remote_sensor_node_image import build_sensor_node_image, select_deployment_image
from remote_sensor_node_operations import (
    clear_remote_data, create_remote_stage, restart_remote_sensor_node,
    run_remote, update_remote_config, update_remote_image,
)
from remote_sensor_node_options import DeployOptions, DeploymentError
from remote_sensor_node_plugin_sync import create_plugin_archive, sync_remote_plugins
from remote_sensor_node_privilege import RemoteEnvironment, run_root_script
from remote_sensor_node_scp import scp_with_progress
from remote_sensor_node_source_sync import create_source_archive, sync_remote_source
from remote_sensor_node_ssh import connect, preflight, prompt_for_ssh_password, require_target
from remote_sensor_node_templates import render_service_unit
from remote_sensor_node_uninstall import uninstall_remote


async def run_build_action(options: DeployOptions) -> None:
    with tempfile.TemporaryDirectory(prefix="fissure-node-build.") as name:
        await build_sensor_node_image(options, Path(name))



async def deploy(options: DeployOptions, asyncssh: Any) -> None:
    target = require_target(options)
    destination = f"{target.username}@{target.hostname}"
    if options.prepare_host:
        password = prompt_for_ssh_password(options)
        async with await connect(asyncssh, options, password) as connection:
            await prepare_remote_host(asyncssh, connection, options, destination)
        return
    if await run_selected_maintenance_action(options, asyncssh, destination):
        return
    await deploy_new_release(options, asyncssh, destination)



async def run_selected_maintenance_action(
    options: DeployOptions,
    asyncssh: Any,
    destination: str,
) -> bool:
    if options.clear_data:
        await run_clear_data_action(options, asyncssh, destination)
        return True
    if options.sync_plugins_dir:
        await run_plugin_sync_action(options, asyncssh, destination)
        return True
    if options.sync_source_dir:
        await run_source_sync_action(options, asyncssh, destination)
        return True
    if options.update_image_file:
        await run_image_update_action(options, asyncssh, destination)
        return True
    if options.restart:
        await run_restart_action(options, asyncssh, destination)
        return True
    if options.update_config_file:
        await run_config_update_action(options, asyncssh, destination)
        return True
    if options.uninstall:
        await run_uninstall_action(options, asyncssh, destination)
        return True
    if options.health_only:
        await run_health_check_action(options, asyncssh, destination)
        return True
    return False



async def run_clear_data_action(
    options: DeployOptions,
    asyncssh: Any,
    destination: str,
) -> None:
    password = prompt_for_ssh_password(options)
    async with await connect(asyncssh, options, password) as connection:
        environment = await preflight(connection, destination)
        await clear_remote_data(connection, options, environment)



async def run_plugin_sync_action(
    options: DeployOptions,
    asyncssh: Any,
    destination: str,
) -> None:
    with tempfile.TemporaryDirectory(prefix="fissure-node-plugins.") as name:
        archive = await asyncio.to_thread(
            create_plugin_archive,
            options.sync_plugins_dir,
            Path(name) / "plugins.tar",
        )
        password = prompt_for_ssh_password(options)
        async with await connect(asyncssh, options, password) as connection:
            environment = await preflight(connection, destination)
            await sync_remote_plugins(
                asyncssh,
                connection,
                options,
                archive,
                environment,
            )



async def run_source_sync_action(
    options: DeployOptions,
    asyncssh: Any,
    destination: str,
) -> None:
    with tempfile.TemporaryDirectory(prefix="fissure-node-source.") as name:
        temp_dir = Path(name)
        archive = await asyncio.to_thread(
            create_source_archive,
            options.sync_source_dir,
            temp_dir / "source.tar",
        )
        password = prompt_for_ssh_password(options)
        async with await connect(asyncssh, options, password) as connection:
            environment = await preflight(connection, destination)
            unit = render_service_unit(
                temp_dir / f"{options.service_name}.service",
                options.remote_dir,
                environment.user,
                environment.group,
                environment.apptainer,
            )
            await sync_remote_source(
                asyncssh,
                connection,
                options,
                archive,
                unit,
                environment,
            )



async def run_image_update_action(
    options: DeployOptions,
    asyncssh: Any,
    destination: str,
) -> None:
    password = prompt_for_ssh_password(options)
    async with await connect(asyncssh, options, password) as connection:
        environment = await preflight(connection, destination)
        await update_remote_image(
            asyncssh,
            connection,
            options,
            options.update_image_file,
            environment,
        )



async def run_restart_action(
    options: DeployOptions,
    asyncssh: Any,
    destination: str,
) -> None:
    password = prompt_for_ssh_password(options)
    async with await connect(asyncssh, options, password) as connection:
        environment = await preflight(connection, destination)
        await restart_remote_sensor_node(connection, options, environment)



async def run_config_update_action(
    options: DeployOptions,
    asyncssh: Any,
    destination: str,
) -> None:
    with tempfile.TemporaryDirectory(prefix="fissure-node-config.") as name:
        password = prompt_for_ssh_password(options)
        async with await connect(asyncssh, options, password) as connection:
            environment = await preflight(connection, destination)
            config_file = prepare_remote_config(
                options.update_config_file,
                Path(name) / "default.yaml",
                connection,
                options.hiprfisr_address,
            )
            await update_remote_config(
                asyncssh,
                connection,
                options,
                config_file,
                environment,
            )



async def run_uninstall_action(
    options: DeployOptions,
    asyncssh: Any,
    destination: str,
) -> None:
    password = prompt_for_ssh_password(options)
    async with await connect(asyncssh, options, password) as connection:
        await uninstall_remote(
            connection,
            destination,
            options.remote_dir,
            options.service_name,
        )



async def run_health_check_action(
    options: DeployOptions,
    asyncssh: Any,
    destination: str,
) -> None:
    password = prompt_for_ssh_password(options)
    async with await connect(asyncssh, options, password) as connection:
        environment = await preflight(connection, destination)
        await wait_for_sensor_node_health(
            connection,
            options,
            environment.privilege,
            require_heartbeat=True,
        )



async def deploy_new_release(
    options: DeployOptions,
    asyncssh: Any,
    destination: str,
) -> None:

    with tempfile.TemporaryDirectory(prefix="fissure-node-deploy.") as name:
        temp_dir = Path(name)
        image = select_deployment_image(options)
        password = prompt_for_ssh_password(options)
        async with await connect(asyncssh, options, password) as connection:
            environment = await prepare_remote_host(
                asyncssh, connection, options, destination,
            )
            config_file = prepare_remote_config(
                options.config_file,
                temp_dir / "default.yaml",
                connection,
                options.hiprfisr_address,
            )
            options = replace(options, config_file=config_file)
            unit = render_service_unit(
                temp_dir / f"{options.service_name}.service",
                options.remote_dir,
                environment.user,
                environment.group,
                environment.apptainer,
            )
            await deploy_release(asyncssh, connection, options, image, unit, environment)



async def deploy_release(
    asyncssh: Any,
    connection: Any,
    options: DeployOptions,
    image: Path,
    unit: Path,
    environment: RemoteEnvironment,
) -> None:
    release_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    stage = await create_remote_stage(connection)
    await upload_payload(asyncssh, connection, stage, options, image, unit)
    args = [
        stage,
        options.remote_dir,
        release_id,
        options.service_name,
        environment.user,
        environment.group,
        environment.apptainer,
    ]
    await run_root_script(
        connection,
        DeploymentUtilities.INSTALL_SCRIPT,
        args,
        environment.privilege,
    )
    await wait_for_sensor_node_health(
        connection,
        options,
        environment.privilege,
        require_heartbeat=False,
    )
    print(f"[✓] Release {release_id} started successfully")



async def upload_payload(
    asyncssh: Any,
    connection: Any,
    stage: str,
    options: DeployOptions,
    image: Path,
    unit: Path,
) -> None:
    files = {
        image: "fissure-sensor-node.sif",
        options.config_file: "default.yaml",
        options.certificates_dir / "clients/client_0.key_secret": "client_0.key_secret",
        options.certificates_dir / "server/server.key": "server.key",
        unit: unit.name,
    }
    print(f"[*] Uploading {image.name} and runtime inputs with SCP")
    try:
        for local, remote_name in files.items():
            destination = (connection, f"{stage}/{remote_name}")
            await scp_with_progress(asyncssh, str(local), destination)
    except Exception as exc:
        await run_remote(connection, f"rm -rf -- {shlex.quote(stage)}", check=False)
        raise DeploymentError(f"SCP upload failed: {exc}") from exc
