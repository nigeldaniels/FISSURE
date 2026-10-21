"""Image-build regressions without package installation or a live Sensor Node."""

import asyncio
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Installer/Remote_Sensor_Node"))

import remote_sensor_node_image as image
import remote_sensor_node_image_check as image_check


class BuildContextTests(unittest.TestCase):
    def test_excludes_cached_and_selected_images_but_preserves_source(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source, destination = root / "source", root / "context"
            paths = (
                "Installer/Remote_Sensor_Node/build/previous.sif",
                "images/selected.sif", "images/keep.txt", "Installer/keep.py",
                "certificates/private", "nested/private.key_secret", "nested/.git/config",
                "Custom_Blocks/maint-3.10/example/CMakeLists.txt",
            )
            for relative in paths:
                path = source / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(relative)
            (source / "source-link").symlink_to("Installer/keep.py")

            image.copy_build_context(source, destination, (source / "images/selected.sif",))

            for relative in paths[:2] + paths[4:7]:
                self.assertFalse((destination / relative).exists(), relative)
            for relative in (paths[2], paths[3], paths[7]):
                self.assertEqual((destination / relative).read_text(), relative)
            self.assertTrue((destination / "source-link").is_symlink())
            self.assertTrue((source / "images/selected.sif").exists())

    def test_output_outside_source_does_not_exclude_matching_source_name(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "source"
            source.mkdir()
            (source / "keep.sif").write_text("fixture")
            image.copy_build_context(source, root / "context", (root / "keep.sif",))
            self.assertTrue((root / "context/keep.sif").is_file())

    def test_context_inside_source_does_not_recurse_into_itself(self):
        with tempfile.TemporaryDirectory() as name:
            source = Path(name)
            (source / "source.py").write_text("pass\n")
            destination = source / "temporary/context"
            destination.parent.mkdir()
            image.copy_build_context(source, destination)
            self.assertTrue((destination / "source.py").is_file())
            self.assertFalse((destination / "temporary/context").exists())


class BuildInvocationTests(unittest.TestCase):
    def test_failed_build_is_not_reported_as_a_created_image(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source, staging = root / "source", root / "staging"
            source.mkdir()
            staging.mkdir()
            options = SimpleNamespace(install_apptainer=False, source_dir=source,
                output_image=source / "custom-output/previous.sif", build_with_sudo=False)
            options.output_image.parent.mkdir()
            options.output_image.write_text("old-image")
            process = SimpleNamespace(wait=AsyncMock(return_value=17))
            with patch.object(image, "ensure_local_apptainer", AsyncMock(return_value="/bin/apptainer")), \
                 patch.object(image.asyncio, "create_subprocess_exec", AsyncMock(return_value=process)) as spawn:
                with self.assertRaises(image.DeploymentError):
                    asyncio.run(image.build_sensor_node_image(options, staging))
            self.assertFalse((staging / "source/custom-output/previous.sif").exists())
            self.assertEqual(spawn.call_args.args[-2:], ("fakeroot", "/bin/apptainer"))


class ValidationDisplayTests(unittest.TestCase):
    def test_invalid_host_temp_paths_are_removed_before_xvfb(self):
        with tempfile.TemporaryDirectory() as name:
            valid = Path(name)
            bad = valid / "host-only"
            environment = {"APPTAINER_CONTAINER": "image.sif", "TMPDIR": str(bad),
                           "TMP": str(valid), "TEMP": str(bad), "DISPLAY": "host:99"}
            with patch.dict(os.environ, environment, clear=True), \
                 patch.object(image_check.shutil, "which", return_value="/usr/bin/xvfb-run"), \
                 patch.object(image_check.os, "execve", side_effect=RuntimeError("re-exec captured")) as execute:
                with self.assertRaisesRegex(RuntimeError, "re-exec captured"):
                    image_check.ensure_apptainer_display()
            actual = execute.call_args.args[2]
            self.assertNotIn("TMPDIR", actual)
            self.assertNotIn("TEMP", actual)
            self.assertEqual(actual["TMP"], str(valid))
            self.assertEqual(actual[image_check.XVFB_ACTIVE_ENV], "1")
            self.assertEqual(execute.call_args.args[1][:2], ["/usr/bin/xvfb-run", "-a"])

    def test_missing_xvfb_fails_clearly(self):
        with patch.dict(os.environ, {"APPTAINER_NAME": "image"}, clear=True), \
             patch.object(image_check.shutil, "which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "xvfb-run is required"):
                image_check.ensure_apptainer_display()

    def test_host_validation_and_reexec_do_not_launch_another_display(self):
        for environment in ({}, {"APPTAINER_NAME": "image", image_check.XVFB_ACTIVE_ENV: "1"}):
            with self.subTest(environment=environment), patch.dict(os.environ, environment, clear=True), \
                 patch.object(image_check.os, "execve") as execute:
                image_check.ensure_apptainer_display()
                execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
