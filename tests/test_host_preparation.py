"""Host preparation contracts, exercised without SSH or package installation."""

import asyncio
import io
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Installer/Remote_Sensor_Node'))

import deploy_remote_sensor_node as cli
import remote_sensor_node_actions as actions
import remote_sensor_node_host as host
from remote_sensor_node_options import DeploymentError, validate_options
from remote_sensor_node_privilege import PrivilegeContext, RemoteEnvironment
from remote_sensor_node_stream import SUPERVISOR, stream_root_command


class HostSelectionTests(unittest.TestCase):
    def test_empty_local_selection_does_not_enable_legacy_defaults(self):
        result = subprocess.run(
            ['bash', str(ROOT / 'Installer/install_apptainer.sh'), '--hardware='],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn('must not be empty', result.stderr)

    def test_supervisor_cancels_children_that_ignore_term(self):
        with tempfile.TemporaryDirectory() as name:
            pid_file = Path(name) / 'child.pid'
            child_script = 'trap "" TERM; echo $$ > "$1"; exec sleep 30'
            process = subprocess.Popen(
                ['bash', '-c', SUPERVISOR, 'supervisor',
                 'bash', '-c', child_script, 'child', str(pid_file)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            try:
                deadline = time.monotonic() + 3
                while not pid_file.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(pid_file.exists())
                child_pid = int(pid_file.read_text())
                process.terminate()
                process.communicate(timeout=6)
                # A killed orphan may remain a zombie until the host reaps it.
                deadline = time.monotonic() + 1
                while _read_process_state(child_pid) not in (None, 'Z') and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertIn(_read_process_state(child_pid), (None, 'Z'))
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.communicate(timeout=6)

    def test_prepare_needs_no_sif_config_or_certificates(self):
        options = cli.parse_options(['user@node', '--prepare-host', '--hardware=uhd,usrp-x300,uhd'])
        validate_options(options)
        self.assertEqual(options.hardware, ('uhd', 'usrp-x300'))
        self.assertNotIn('--check-only', host.host_command('/stage', 'user', options))

    def test_default_hardware_and_legacy_target(self):
        options = cli.parse_options(['--target=node', '--prepare-host'])
        validate_options(options)
        self.assertEqual(options.target.username, 'root')
        self.assertEqual(options.hardware, ())

    def test_conflicting_actions_and_selection_fail_before_ssh(self):
        for arguments in (
            ['node', '--prepare-host', '--deploy'],
            ['node', '--restart', '--hardware=hackrf'],
            ['--build', '--hardware=uhd'],
            ['node', '--prepare-host', '--skip-host-prep'],
            ['node', '--deploy', '--hardware=wifi', '--skip-host-prep'],
            ['node', '--prepare-host', '--hardware=none,uhd'],
            ['node', '--prepare-host', '--hardware=uhd,'],
        ):
            with self.subTest(arguments=arguments), self.assertRaises(DeploymentError):
                validate_options(cli.parse_options(arguments))

    def test_no_install_flag_survives_transport_boundary(self):
        options = cli.parse_options(['node', '--prepare-host', '--no-install-apptainer'])
        self.assertIn('--no-install-apptainer', host.host_command('/stage', 'user', options))

    def test_dispatch_selects_each_recipe_once_with_explicit_user(self):
        # Override the low-level recipes after sourcing; no host command is run.
        script = f'source {shlex.quote(str(ROOT / "Installer/Host/hardware.sh"))}\n'
        script += '''host_root() { echo "root:$*"; }
prepare_uhd() { echo "uhd:$1"; }
prepare_usrp_x300() { echo x300; }
prepare_hackrf() { echo "hackrf:$1"; }
prepare_hardware uhd,usrp-x300,uhd,hackrf nodeuser /staged/source
'''
        result = subprocess.run(['bash', '-eu', '-c', script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(),
                         ['root:apt-get update', 'uhd:nodeuser', 'x300', 'hackrf:/staged/source'])

    def test_check_only_never_runs_package_manager(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            for executable, contents in {
                'apptainer': '#!/bin/bash\necho APPTAINER_SUID_INSTALL=1\n',
                'apt-get': '#!/bin/bash\necho UNEXPECTED_INSTALL >&2\nexit 99\n',
            }.items():
                path = directory / executable
                path.write_text(contents)
                path.chmod(0o755)
            result = subprocess.run(
                ['bash', str(ROOT / 'Installer/Host/prepare_host.sh'), '--check-only'],
                env={**os.environ, 'PATH': f'{directory}:{os.environ["PATH"]}'},
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn('UNEXPECTED_INSTALL', result.stderr)

    def test_staged_kit_contains_only_installer_assets(self):
        with tempfile.TemporaryDirectory() as name:
            archive = Path(name) / 'kit.tar'
            host.create_installer_archive(archive)
            with tarfile.open(archive) as handle:
                names = handle.getnames()
                self.assertIn('Installer/Host/prepare_host.sh', names)
                self.assertIn('Tools/53-hackrf.rules', names)
                self.assertTrue(all(n.startswith('Installer/Host/') or n in (
                    'Installer/install_apptainer_package.sh', 'Tools/53-hackrf.rules') for n in names))
                self.assertTrue(all(member.isfile() for member in handle))


class RemotePreparationTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_install_cleans_stage_and_does_not_deploy(self):
        options = cli.parse_options(['node', '--prepare-host'])
        environment = RemoteEnvironment('user', 'users', '', PrivilegeContext('root'))
        with (
            patch.object(host, 'inspect_remote_environment', AsyncMock(return_value=environment)),
            patch.object(host, 'create_remote_stage', AsyncMock(return_value='/tmp/kit')),
            patch.object(host, 'scp_with_progress', AsyncMock()),
            patch.object(host, 'run_remote', AsyncMock()) as run,
            patch.object(host, 'stream_root_command', AsyncMock(side_effect=RuntimeError('failed'))),
        ):
            with self.assertRaisesRegex(host.HostPreparationError, 'failed'):
                await host.prepare_remote_host(None, object(), options, 'node')
        self.assertIn('rm -rf -- /tmp/kit', run.await_args.args[1])

    async def test_cancellation_cleans_stage(self):
        options = cli.parse_options(['node', '--prepare-host'])
        environment = RemoteEnvironment('user', 'users', '', PrivilegeContext('root'))
        with (
            patch.object(host, 'inspect_remote_environment', AsyncMock(return_value=environment)),
            patch.object(host, 'create_remote_stage', AsyncMock(return_value='/tmp/kit')),
            patch.object(host, 'scp_with_progress', AsyncMock(side_effect=asyncio.CancelledError)),
            patch.object(host, 'run_remote', AsyncMock()) as run,
        ):
            with self.assertRaises(asyncio.CancelledError):
                await host.prepare_remote_host(None, object(), options, 'node')
        self.assertIn('rm -rf -- /tmp/kit', run.await_args.args[1])

    async def test_maintenance_dispatch_does_not_prepare_host(self):
        options = cli.parse_options(['node', '--restart'])
        with (
            patch.object(actions, 'run_restart_action', AsyncMock()) as restart,
            patch.object(actions, 'prepare_remote_host', AsyncMock()) as prepare,
        ):
            await actions.deploy(options, object())
        restart.assert_awaited_once()
        prepare.assert_not_awaited()

    async def test_stream_is_chunked_and_password_is_only_stdin(self):
        process = SimpleNamespace(
            stdin=SimpleNamespace(write=lambda value: written.append(value), write_eof=lambda: None),
            stdout=SimpleNamespace(read=AsyncMock(side_effect=['output', ''])),
            stderr=SimpleNamespace(read=AsyncMock(return_value='')),
            exit_status=0, wait_closed=AsyncMock(),
        )
        connection = SimpleNamespace(create_process=AsyncMock(return_value=process))
        written = []
        with patch('sys.stdout', io.StringIO()):
            await stream_root_command(connection, ['bash', '/kit/script'],
                                      PrivilegeContext('password', 'secret-value'))
        self.assertEqual(written, ['secret-value\n'])
        self.assertNotIn('secret-value', connection.create_process.await_args.args[0])
        self.assertEqual(process.stdout.read.await_args.args, (4096,))


def _read_process_state(pid):
    try:
        return Path(f'/proc/{pid}/stat').read_text().split()[2]
    except (FileNotFoundError, ProcessLookupError):
        return None


if __name__ == '__main__':
    unittest.main()
