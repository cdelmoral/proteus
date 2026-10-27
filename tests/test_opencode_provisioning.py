"""Run real OpenCode Ansible tasks and launcher with isolated vendor artifacts."""
import functools
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import threading
import unittest

from test_enroll import ROOT


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@unittest.skipUnless(shutil.which('ansible-playbook'), 'Ansible is required')
class OpenCodeProvisioningTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.home = self.directory / 'guest'
        self.home.mkdir()
        self.prefix = self.home / 'baseline'
        self.package = self.prefix / 'lib/node_modules/opencode-ai'
        (self.package / 'bin').mkdir(parents=True)
        (self.package / 'bin/opencode').write_text('old npm command')
        (self.prefix / 'bin').mkdir()
        (self.prefix / 'bin/opencode').symlink_to('../lib/node_modules/opencode-ai/bin/opencode')
        self.command = self.home / '.local/bin/opencode'
        self.command.parent.mkdir(parents=True)
        self.command.symlink_to(self.prefix / 'bin/opencode')
        self.state = {}
        for relative in ['.config/opencode/opencode.json', '.local/share/opencode/auth.json',
                         '.local/state/opencode/history', '.cache/opencode/cache',
                         '.config/opencode/skills/custom/SKILL.md', '.opencode/custom']:
            path = self.home / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('preserve ' + relative)
            self.state[path] = path.read_bytes()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(
            QuietHandler, directory=str(self.directory)))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.release('1.2.3')
        self.playbook = self.directory / 'playbook.json'
        self.playbook.write_text(json.dumps([{
            'name': 'Exercise OpenCode Provisioning', 'hosts': 'all', 'gather_facts': False,
            'vars_files': [str(ROOT / 'provisioning/group_vars/all.yml')],
            'tasks': [{'ansible.builtin.import_tasks': str(ROOT / 'provisioning/tasks/opencode.yml')}]}]))
        self.variables = {
            'ansible_facts': {'system': 'Linux', 'architecture': 'aarch64', 'user_dir': str(self.home)},
            'ansible_python_interpreter': os.sys.executable,
            'managed_node': {'stdout': str(self.prefix)},
            'opencode_release_url': self.url + '/release.json',
        }

    def release(self, version, digest=None, broken=False):
        # Simulate only the vendor binary; Ansible downloads, digest verification,
        # extraction, migration, and launcher execution are real.
        binary = (f'#!/bin/sh\necho {version}\n' if not broken else '#!/bin/sh\nexit 42\n').encode()
        archive = self.directory / 'opencode.tar.gz'
        with tarfile.open(archive, 'w:gz') as output:
            info = tarfile.TarInfo('opencode')
            info.mode = 0o755
            info.size = len(binary)
            output.addfile(info, io.BytesIO(binary))
        (self.directory / 'release.json').write_text(json.dumps({
            'tag_name': 'v' + version, 'assets': [{
                'name': 'opencode-linux-arm64.tar.gz',
                'browser_download_url': self.url + '/opencode.tar.gz',
                'digest': digest or 'sha256:' + hashlib.sha256(archive.read_bytes()).hexdigest(),
            }]}))

    def provision(self, **variables):
        result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local',
                                 str(self.playbook), '-e', json.dumps({**self.variables, **variables})],
                                capture_output=True, text=True, timeout=60)
        return result

    def assert_state(self):
        for path, content in self.state.items():
            self.assertEqual(path.read_bytes(), content)

    def test_migrates_repeats_and_updates_preserving_state(self):
        for version in ['1.2.3', '1.2.3', '1.2.4']:
            self.release(version)
            result = self.provision()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            # Dotfiles owns the launcher, installed after development tools.
            if not self.command.exists():
                self.command.symlink_to(ROOT / 'dotfiles/home/.local/bin/opencode')
            result = subprocess.run(['opencode', '--version'], env={
                'HOME': str(self.home), 'PATH': str(self.command.parent)}, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), version)
            self.assertFalse(self.package.exists())
            self.assertFalse((self.prefix / 'bin/opencode').is_symlink())
            self.assert_state()

    def test_failed_download_or_candidate_preserves_previous_installation(self):
        installed = self.home / '.local/share/proteus/opencode/opencode'
        installed.parent.mkdir(parents=True)
        installed.write_bytes(b'previous standalone installation')
        for options in [{'digest': 'missing-digest'},
                        {'digest': 'sha256:' + '0' * 64}, {'broken': True}]:
            self.release('1.2.4', **options)
            result = self.provision()
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(self.command.read_text(), 'old npm command')
            self.assertEqual(installed.read_bytes(), b'previous standalone installation')
            self.assert_state()

    def test_rejects_unsupported_platform_and_preserves_unrelated_command(self):
        result = self.provision(ansible_facts={
            'system': 'Linux', 'architecture': 'x86_64', 'user_dir': str(self.home)})
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.package.exists())
        custom = self.home / 'custom-opencode'
        custom.write_text('user command')
        self.command.unlink()
        self.command.symlink_to(custom)
        result = self.provision()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.command.read_text(), 'user command')
        self.assert_state()


class OpenCodeLauncherTest(unittest.TestCase):
    def test_preserves_project_environment_arguments_children_and_exit_status(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            binary = home / '.local/share/proteus/opencode/opencode'
            binary.parent.mkdir(parents=True)
            # A project-selected child command, with no baseline Node on PATH.
            project = home / 'project'
            project.mkdir()
            (project / '.nvmrc').write_text('99.0.0\n')
            node = project / 'node'
            node.write_text('#!/bin/sh\nprintf "project-node\\n"\n')
            node.chmod(0o755)
            binary.write_text('#!/bin/sh\n'
                              'printf "%s\\n" "$OPENCODE_DISABLE_AUTOUPDATE" "$PATH" "$@"\n'
                              'node\nexit 37\n')
            binary.chmod(0o755)
            result = subprocess.run([str(ROOT / 'dotfiles/home/.local/bin/opencode'),
                                     'argument with spaces', '', '--flag'], cwd=project,
                                    env={'HOME': directory, 'PATH': str(project),
                                         'OPENCODE_DISABLE_AUTOUPDATE': 'false'},
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 37, result.stderr)
            self.assertEqual(result.stdout.splitlines(), [
                'true', str(project), 'argument with spaces', '', '--flag', 'project-node'])
