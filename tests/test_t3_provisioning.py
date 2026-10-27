"""Run T3's actual Ansible tasks against an isolated vendor boundary."""
import functools
import hashlib
import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import tarfile
import unittest

from test_enroll import ROOT


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@unittest.skipUnless(shutil.which('ansible-playbook'), 'Ansible is required')
class T3ProvisioningTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.home = self.directory / 'guest'
        self.system = self.directory / 'system'
        (self.system / 'bin').mkdir(parents=True)
        self.state = {
            '.t3/userdata/secrets/credential': 'preserve-credential',
            '.t3/userdata/server-runtime.json': '{"pid": 1234, "serviceManaged": true}',
            '.t3/runtime/service-state.json': '{"activeVersion": "0.0.45"}',
            '.t3/runtime/versions/0.0.45/t3': 'preserve-service-runtime',
            '.config/systemd/user/t3code.service': 'preserve-unit',
            '.t3/config.json': 'preserve-configuration',
        }
        for path, content in self.state.items():
            destination = self.home / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content)
        self.vendor = self.directory / 'vendor'
        self.publish('1.2.3')
        self.server = http.server.ThreadingHTTPServer(
            ('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(self.vendor)))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.tasks = self.directory / 't3.yml'
        self.tasks.write_text((ROOT / 'provisioning/tasks/t3.yml').read_text()
                              .replace('/usr/local', str(self.system))
                              .replace('become: true', 'become: false'))
        self.playbook = self.directory / 'playbook.yml'
        self.playbook.write_text(json.dumps([{
            'name': 'Exercise T3 Provisioning', 'hosts': 'all', 'gather_facts': False,
            'vars_files': [str(ROOT / 'provisioning/group_vars/all.yml')],
            'tasks': [{'ansible.builtin.import_tasks': str(self.tasks)}]}]))
        self.variables = {
            'ansible_facts': {'system': 'Linux', 'architecture': 'aarch64',
                              'user_dir': str(self.home), 'env': {'PATH': '/usr/bin:/bin'}},
            'ansible_python_interpreter': os.sys.executable,
            't3_distribution_url': f'http://127.0.0.1:{self.server.server_port}',
            't3_release_url': f'http://127.0.0.1:{self.server.server_port}/latest',
        }

    def publish(self, version, bad_digest=False, invalid_executable=False):
        release = self.vendor / ('v' + version)
        release.mkdir(parents=True)
        stage = self.directory / ('stage-' + version)
        stage.mkdir()
        binary = stage / 't3'
        # Exercise real archive/checksum/install boundaries; this executable is
        # simulated and cannot prove Linux ARM64 vendor compatibility.
        binary.write_text(f'''#!{os.sys.executable}
import os, pathlib, subprocess, sys
assert pathlib.Path(__file__).resolve().with_name('asset').read_text() == 'required-asset'
if sys.argv[1:] == ['--version']:
    if {invalid_executable!r}:
        sys.exit(92)
    print('{version}')
elif sys.argv[1:] == ['fixture-child']:
    sys.exit(subprocess.call(['node', '--version']))
else:
    sys.exit(91)  # No connect, service, update, or enrollment during Provisioning.
''')
        binary.chmod(0o755)
        (stage / 'asset').write_text('required-asset')
        archive = release / f't3-{version}-linux-arm64.tar.gz'
        with tarfile.open(archive, 'w:gz') as bundle:
            bundle.add(stage, arcname=f't3-{version}-linux-arm64')
        (self.vendor / 'latest').write_text(json.dumps({'tag_name': 'v' + version}))
        digest = '0' * 64 if bad_digest else hashlib.sha256(archive.read_bytes()).hexdigest()
        (release / 'SHA256SUMS').write_text(f'{digest}  {archive.name}\n')

    def provision(self, **variables):
        return subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local',
                               str(self.playbook), '-e', json.dumps({**self.variables, **variables})],
                              capture_output=True, text=True, timeout=90)

    def assert_state(self):
        for path, content in self.state.items():
            self.assertEqual((self.home / path).read_text(), content)

    def run_t3(self, *args, path=None, cwd=None):
        return subprocess.run(['t3', *args], env={'HOME': str(self.home),
                              'PATH': path or str(self.system / 'bin')}, cwd=cwd,
                              capture_output=True, text=True, timeout=15)

    def test_install_repeat_upgrade_and_preserve_user_state(self):
        for version in ('1.2.3', '1.2.3', '1.2.4'):
            if version == '1.2.4':
                self.publish(version)
            result = self.provision()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = self.run_t3('--version')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(version, result.stdout)
            self.assert_state()
        for selection in ('v20', 'v22', 'missing'):
            project = self.directory / selection
            project.mkdir()
            (project / '.node-version').write_text(selection)
            project_bin = project / 'bin'
            project_bin.mkdir()
            node = project_bin / 'node'
            node.write_text('#!/bin/sh\n' + ('exit 42\n' if selection == 'missing' else f'echo {selection}\n'))
            node.chmod(0o755)
            path = f'{self.system / "bin"}:{project_bin}'
            self.assertEqual(self.run_t3('--version', path=path, cwd=project).returncode, 0)
            child = self.run_t3('fixture-child', path=path, cwd=project)
            self.assertEqual(child.returncode, 42 if selection == 'missing' else 0)
            if selection != 'missing':
                self.assertEqual(child.stdout.strip(), selection)

    @unittest.skipUnless(shutil.which('npm') and shutil.which('node'), 'npm is required for migration')
    def test_migrates_real_npm_packages_from_retained_node_prefixes(self):
        # A nested project/global prefix is not a Provisioning-owned install.
        unmanaged = (self.home / '.local/share/mise/installs/node/22.0.0'
                     / 'workspace/lib/node_modules/t3')
        unmanaged.mkdir(parents=True)
        (unmanaged / 'package.json').write_text('{"name":"t3"}')
        prefixes = []
        for version in ('22.0.0', '24.0.0'):
            prefix = self.home / '.local/share/mise/installs/node' / version
            package = prefix / 'lib/node_modules/t3'
            package.mkdir(parents=True)
            (package / 'package.json').write_text(json.dumps({
                'name': 't3', 'version': '0.0.0',
                'bin': {'t3': 'cli.js'}}))
            (package / 'cli.js').write_text('obsolete-distribution')
            (prefix / 'bin').mkdir()
            (prefix / 'bin/t3').symlink_to(package / 'cli.js')
            for command in ('npm', 'node'):
                source = Path(shutil.which(command)).resolve()
                if command == 'npm':
                    cli = source.parent.parent / 'lib/node_modules/npm/bin/npm-cli.js'
                    if cli.exists():
                        source = cli
                (prefix / 'bin' / command).symlink_to(source)
            other = prefix / 'lib/node_modules/preserve-package'
            other.mkdir()
            (other / 'package.json').write_text('{"name":"preserve-package","version":"1.0.0"}')
            prefixes.append(prefix)
        (self.home / '.local/bin').mkdir(parents=True)
        (self.home / '.local/bin/t3').symlink_to(prefixes[-1] / 'bin/t3')
        for _ in range(2):
            result = self.provision()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(self.run_t3('--version').returncode, 0)
            for prefix in prefixes:
                self.assertFalse((prefix / 'lib/node_modules/t3').exists())
                self.assertFalse((prefix / 'bin/t3').is_symlink())
                self.assertTrue((prefix / 'lib/node_modules/preserve-package/package.json').exists())
                self.assertTrue((prefix / 'bin/node').exists())
            self.assertTrue((unmanaged / 'package.json').exists())
            self.assert_state()

    def test_invalid_artifact_preserves_active_command_and_state(self):
        result = self.provision()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.publish('1.2.4', bad_digest=True)
        result = self.provision()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('1.2.3', self.run_t3('--version').stdout)
        self.assert_state()
        (self.vendor / 'latest').write_text(json.dumps({'tag_name': '../unsafe'}))
        self.assertNotEqual(self.provision().returncode, 0)
        self.assertIn('1.2.3', self.run_t3('--version').stdout)
        self.assert_state()

    def test_unusable_executable_preserves_active_command_and_state(self):
        self.assertEqual(self.provision().returncode, 0)
        self.publish('1.2.4', invalid_executable=True)
        self.assertNotEqual(self.provision().returncode, 0)
        self.assertIn('1.2.3', self.run_t3('--version').stdout)
        self.assert_state()

    def test_unsupported_architecture_fails_without_installing(self):
        facts = {**self.variables['ansible_facts'], 'architecture': 'x86_64'}
        result = self.provision(ansible_facts=facts)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.system / 'bin/t3').exists())
        self.assert_state()
