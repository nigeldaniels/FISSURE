"""Build or select the Sensor Node image used by the deployment CLI."""

import asyncio
from pathlib import Path
import shlex
import shutil

from remote_sensor_node_local_apptainer import ensure_local_apptainer
from remote_sensor_node_options import DeployOptions, DeploymentError
from remote_sensor_node_templates import (
    APPTAINER_TEMPLATE,
    render_apptainer_definition,
)


async def build_sensor_node_image(options: DeployOptions, temp_dir: Path) -> Path:
    """Build a fresh SIF at the requested output path."""
    apptainer = await ensure_local_apptainer(options.install_apptainer)
    source = temp_dir / "source"
    await asyncio.to_thread(
        copy_build_context, options.source_dir, source, (options.output_image,)
    )
    definition = render_apptainer_definition(
        source,
        temp_dir / APPTAINER_TEMPLATE.stem,
    )
    options.output_image.parent.mkdir(parents=True, exist_ok=True)
    builder = Path(__file__).resolve().parent.parent / "Apptainer/build_image.sh"
    command = [
        "bash", str(builder), "sif", str(options.output_image), str(definition),
        "root" if options.build_with_sudo else "fakeroot", apptainer,
    ]
    if options.build_with_sudo:
        command.insert(0, "sudo")

    print(f"[*] Building {options.output_image}")
    process = await asyncio.create_subprocess_exec(*command)
    if await process.wait():
        raise DeploymentError(f"Build failed: {shlex.join(command)}")
    image = options.output_image.resolve()
    print(f"[✓] Built Sensor Node image {image}")
    return image


def select_deployment_image(options: DeployOptions) -> Path:
    """Select a supplied SIF or the output from an earlier build."""
    image = options.image_file or options.output_image
    if not image.is_file():
        raise DeploymentError(
            f"Deployment image is not a file: {image}. "
            "Run --build first or provide --image."
        )
    print(f"[✓] Using existing image {image}")
    return image.resolve()


def copy_build_context(
    source: Path,
    destination: Path,
    excluded_paths: tuple[Path, ...] = (),
) -> None:
    source = source.resolve()
    root_exclusions = {
        ".agents",
        ".codex",
        ".env",
        ".git",
        ".idea",
        ".venv",
        "Logs",
        "artifacts",
        "artifacts_node",
        "artifacts_system",
        "build",
        "certificates",
        "logs",
    }
    excluded_relative_paths = {Path("Installer/Remote_Sensor_Node/build")}
    for path in (*excluded_paths, destination):
        try:
            excluded_relative_paths.add(path.resolve().relative_to(source))
        except ValueError:
            # Outputs and temporary contexts normally live outside the source.
            continue

    def ignore(directory: str, names: list[str]) -> set[str]:
        relative_directory = Path(directory).resolve().relative_to(source)
        ignored = {
            name
            for name in names
            if name in {".git", ".pytest_cache", "__pycache__"}
        }
        if not relative_directory.parts:
            ignored.update(root_exclusions.intersection(names))
        # Do not copy a previous multi-gigabyte image into its replacement, or
        # recursively copy the destination if TMPDIR is inside the checkout.
        ignored.update(
            name for name in names
            if relative_directory / name in excluded_relative_paths
        )
        ignored.update(name for name in names if name.endswith(".key_secret"))
        return ignored

    shutil.copytree(source, destination, symlinks=True, ignore=ignore)
