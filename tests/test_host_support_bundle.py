"""Offline package boundaries using tiny real Debian packages and APT simulation."""

import hashlib
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / 'Installer/Host'
sys.path.insert(0, str(ROOT / 'Installer/Remote_Sensor_Node'))

import deploy_remote_sensor_node as cli
from remote_sensor_node_host import create_installer_archive, host_command
from remote_sensor_node_options import DeploymentError, validate_options


def shell(script):
    sources = '\n'.join(f'source {shlex.quote(str(HOST / name))}' for name in
                        ('common.sh', 'apptainer_packages.sh', 'support_bundle.sh'))
    return subprocess.run(['bash', '-euo', 'pipefail', '-c', sources + '\n' + script],
                          capture_output=True, text=True)


def build_package(directory, name, architecture='all', dependencies=''):
    tree = directory / name
    (tree / 'DEBIAN').mkdir(parents=True)
    control = (f'Package: {name}\nVersion: 99.0\nArchitecture: {architecture}\n'
               'Maintainer: FISSURE Test <test@example.invalid>\nDescription: Test fixture\n')
    if dependencies:
        control += f'Depends: {dependencies}\n'
    (tree / 'DEBIAN/control').write_text(control)
    output = directory / 'bundle/packages' / f'{name}_99.0_{architecture}.deb'
    subprocess.run(['dpkg-deb', '--build', str(tree), str(output)],
                   check=True, capture_output=True)
    return output


def refresh_bundle(bundle):
    result = subprocess.run(['dpkg-scanpackages', 'packages', '/dev/null'],
                            cwd=bundle, capture_output=True, text=True, check=True)
    (bundle / 'Packages').write_text(result.stdout.replace('Filename: packages/', 'Filename: ./packages/'))
    lines = []
    for path in sorted(bundle.rglob('*')):
        if path.is_file() and path.name != 'SHA256SUMS':
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            lines.append(f'{digest}  {path.relative_to(bundle)}\n')
    (bundle / 'SHA256SUMS').write_text(''.join(lines))


@unittest.skipUnless(shutil.which('dpkg-scanpackages'), 'Debian package tools required')
class BundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os_release = Path('/etc/os-release').read_text()
        if 'ID=ubuntu\n' not in os_release or 'VERSION_ID="24.04"' not in os_release:
            raise unittest.SkipTest('Offline proof targets Ubuntu 24.04')

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.bundle = self.directory / 'bundle'
        (self.bundle / 'packages').mkdir(parents=True)
        self.architecture = subprocess.check_output(['dpkg', '--print-architecture'], text=True).strip()
        (self.bundle / 'bundle.info').write_text(
            f'format=1\nos=ubuntu\nversion=24.04\narchitecture={self.architecture}\n')
        (self.bundle / 'package-versions.txt').write_text('Fixture packages: 99.0\n')
        build_package(self.directory, 'apptainer-suid', dependencies='fissure-proof-dependency (= 99.0)')
        self.dependency = build_package(self.directory, 'fissure-proof-dependency')
        refresh_bundle(self.bundle)

    def validate(self):
        return shell(f'validate_support_bundle {shlex.quote(str(self.bundle))}')

    def simulate(self):
        workspace = self.directory / 'apt-state'
        workspace.mkdir()
        return shell(f'validate_support_bundle {shlex.quote(str(self.bundle))}\n'
                     f'prepare_offline_apt {shlex.quote(str(self.bundle))} {shlex.quote(str(workspace))}')

    def test_valid_bundle_resolves_locally_without_installation(self):
        result = self.simulate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Inst fissure-proof-dependency', result.stdout)
        self.assertNotIn('https:', result.stdout)
        self.assertIn('only a simulation', result.stdout + result.stderr)
        config = (self.directory / 'apt-state/apt.conf').read_text()
        self.assertIn('Dir::Etc::parts', config)
        self.assertEqual((self.directory / 'apt-state/sources.list').read_text().count('file:'), 1)

    def test_missing_dependency_is_not_fetched_from_host_sources(self):
        self.dependency.unlink()
        refresh_bundle(self.bundle)
        result = self.simulate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('fissure-proof-dependency', result.stdout + result.stderr)

    def test_corruption_is_rejected_before_apt(self):
        with self.dependency.open('ab') as handle:
            handle.write(b'corrupt')
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('checksum failure', result.stderr)

    def test_wrong_architecture_is_rejected(self):
        wrong = 'arm64' if self.architecture == 'amd64' else 'amd64'
        metadata = self.bundle / 'bundle.info'
        metadata.write_text(metadata.read_text().replace(self.architecture, wrong))
        refresh_bundle(self.bundle)
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('architecture does not match', result.stderr)

    def test_links_and_unchecked_files_are_rejected(self):
        (self.bundle / 'linked').symlink_to('/etc/passwd')
        self.assertNotEqual(self.validate().returncode, 0)
        (self.bundle / 'linked').unlink()
        (self.bundle / 'unexpected').write_text('extra')
        self.assertNotEqual(self.validate().returncode, 0)

    def test_checksum_path_traversal_is_rejected(self):
        with (self.bundle / 'SHA256SUMS').open('a') as handle:
            handle.write('0' * 64 + '  ../../etc/passwd\n')
        result = self.validate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Invalid bundle checksum entry', result.stderr)

    def test_bundle_flag_implies_offline_and_is_transferred(self):
        options = cli.parse_options(['node', '--prepare-host', f'--host-support={self.bundle}'])
        validate_options(options)
        self.assertTrue(options.offline)
        command = host_command('/staging', 'nodeuser', options)
        self.assertIn('--offline', command)
        self.assertIn('--host-support=/staging/host-support', command)
        archive = self.directory / 'transfer.tar'
        create_installer_archive(archive, self.bundle)
        self.assertGreater(archive.stat().st_size, self.dependency.stat().st_size)

    def test_bundle_creation_does_not_overwrite_existing_output(self):
        result = subprocess.run(['bash', str(HOST / 'prepare_support_bundle.sh'),
                                 f'--output={self.bundle}'], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('new --output directory', result.stderr)
        self.assertTrue(self.dependency.exists())

    def test_bundle_publication_does_not_replace_existing_directory(self):
        output = self.directory / 'published bundle'
        command = f'publish_support_bundle {shlex.quote(str(self.bundle))} {shlex.quote(str(output))}'
        result = shell(command)
        self.assertEqual(result.returncode, 0, result.stderr)
        (output / 'operator-file').touch()
        result = shell(command)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue((output / 'operator-file').exists())
        self.assertFalse(list(self.directory.glob('.fissure-support.*')))


class OfflineOptionsTests(unittest.TestCase):
    def test_empty_bundle_option_cannot_fall_back_to_online(self):
        with self.assertRaisesRegex(DeploymentError, 'bundle directory'):
            cli.parse_options(['node', '--prepare-host', '--host-support='])

    def test_offline_hardware_and_maintenance_are_rejected(self):
        for arguments in (['node', '--prepare-host', '--offline', '--hardware=rtlsdr'],
                          ['node', '--restart', '--offline'], ['--build', '--offline']):
            with self.subTest(arguments=arguments), self.assertRaises(DeploymentError):
                validate_options(cli.parse_options(arguments))


if __name__ == '__main__':
    unittest.main()
