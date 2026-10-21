"""Exercise shared installer boundaries without installing host packages."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "Installer"


class SharedBuildTests(unittest.TestCase):
    def test_build_preserves_arguments_and_propagates_failure(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            executable = directory / "apptainer"
            executable.write_text('#!/bin/bash\nprintf "%s\\n" "$@"\nexit 17\n')
            executable.chmod(0o755)
            definition = directory / "source with spaces.def"
            definition.touch()
            output = directory / "image with spaces.sif"
            result = subprocess.run(
                ["bash", str(INSTALLER / "Apptainer/build_image.sh"),
                 "sif", str(output), str(definition), "fakeroot"],
                env={**os.environ, "PATH": f"{directory}:{os.environ['PATH']}"},
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 17)
            self.assertEqual(result.stdout.splitlines(),
                             ["build", "--force", "--fakeroot", str(output), str(definition)])

    def test_invalid_build_input_never_invokes_apptainer(self):
        result = subprocess.run(
            ["bash", str(INSTALLER / "Apptainer/build_image.sh"),
             "invalid", "/unused", "/unused"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("Unsupported image format", result.stderr)

    def test_explicit_binary_survives_a_different_privileged_path(self):
        with tempfile.TemporaryDirectory() as name:
            binary = Path(name) / "custom-apptainer"
            binary.write_text('#!/bin/bash\necho custom-binary\n')
            binary.chmod(0o755)
            definition = Path(name) / "image.def"
            definition.touch()
            result = subprocess.run(
                ["bash", str(INSTALLER / "Apptainer/build_image.sh"),
                 "sif", "/unused.sif", str(definition), "root", str(binary)],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "custom-binary")


class LocalInstallerTests(unittest.TestCase):
    def test_help_does_not_run_installation(self):
        result = subprocess.run(
            ["bash", str(INSTALLER / "install_apptainer.sh"), "--help"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for option in ("--xpra", "--mode", "--uhd", "--auto-launch-sensor-node"):
            self.assertIn(option, result.stdout)


if __name__ == "__main__":
    unittest.main()
