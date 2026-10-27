"""Run Claude's actual Ansible tasks against an isolated vendor boundary."""
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
import unittest

from test_enroll import ROOT


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@unittest.skipUnless(shutil.which('ansible-playbook'), 'Ansible is required')
class ClaudeProvisioningTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.home = self.directory / 'guest'
        self.system = self.directory / 'system'
        (self.system / 'bin').mkdir(parents=True)
        self.state = {
            '.claude/.credentials.json': '{"fixture": "preserve-credential"}',
            '.claude/settings.json': '{"fixture": "preserve-settings"}',
            '.claude.json': '{"fixture": "preserve-enrollment"}',
            '.claude/projects/history': 'preserve-session',
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
        self.tasks = self.directory / 'claude.yml'
        self.tasks.write_text((ROOT / 'provisioning/tasks/claude.yml').read_text()
                              .replace('/usr/local', str(self.system))
                              .replace('/etc/claude-code', str(self.system / 'settings'))
                              .replace('become: true', 'become: false')
                              .replace('owner: root', 'owner: ' + str(os.getuid()))
                              .replace('group: root', 'group: ' + str(os.getgid())))
        self.playbook = self.directory / 'playbook.yml'
        self.playbook.write_text(json.dumps([{
            'name': 'Exercise Claude Provisioning', 'hosts': 'all', 'gather_facts': False,
            'vars_files': [str(ROOT / 'provisioning/group_vars/all.yml')],
            'tasks': [{'ansible.builtin.import_tasks': str(self.tasks)}]}]))
        self.variables = {
            'ansible_facts': {'system': 'Linux', 'architecture': 'aarch64',
                              'user_dir': str(self.home), 'env': {'PATH': '/usr/bin:/bin'}},
            'ansible_python_interpreter': os.sys.executable,
            'claude_distribution_url': f'http://127.0.0.1:{self.server.server_port}',
        }

    def publish(self, version, bad_digest=False):
        binary = self.vendor / version / 'linux-arm64/claude'
        binary.parent.mkdir(parents=True)
        # The distribution is simulated, not Ansible's download, checksum,
        # migration, invocation, or link operations. This does not prove ARM64
        # compatibility; that requires the real Lima acceptance flow.
        binary.write_text(f'''#!{os.sys.executable}
import json, os, pathlib, subprocess, sys
home = pathlib.Path.home()
args = sys.argv[1:]
marketplace = home / '.claude/fixture-marketplace'
if args == ['--version']:
    print('{version} (Claude Code fixture)')
elif args == ['plugin', 'marketplace', 'list', '--json']:
    print(json.dumps([{{'name': 'claude-plugins-official'}}] if marketplace.exists() else []))
elif args == ['plugin', 'marketplace', 'add', 'anthropics/claude-plugins-official']:
    assert os.environ['CLAUDE_CODE_PLUGIN_PREFER_HTTPS'] == '1'
    marketplace.write_text('registered')
elif args == ['plugin', 'install', 'mattpocock-skills@claude-plugins-official']:
    assert marketplace.exists()
    (home / '.claude/fixture-skills').write_text('installed')
elif args == ['auth', 'status']:
    assert (home / '.claude/.credentials.json').exists()
    print('fixture authenticated')
elif args == ['fixture-child']:
    sys.exit(subprocess.call(['node', '--version']))
else:
    sys.exit(91)  # Provisioning must never log in.
''')
        (self.vendor / 'latest').write_text(version + '\n')
        (self.vendor / version / 'manifest.json').write_text(json.dumps({
            'platforms': {'linux-arm64': {'checksum': '0' * 64 if bad_digest else
                                         hashlib.sha256(binary.read_bytes()).hexdigest()}}}))

    def provision(self, **variables):
        return subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local',
                               str(self.playbook), '-e', json.dumps({**self.variables, **variables})],
                              capture_output=True, text=True, timeout=90)

    def assert_state(self):
        for path, content in self.state.items():
            self.assertEqual((self.home / path).read_text(), content)

    def run_claude(self, *args, path=None, cwd=None):
        return subprocess.run(['claude', *args], env={'HOME': str(self.home),
                              'PATH': path or str(self.system / 'bin')}, cwd=cwd,
                              capture_output=True, text=True, timeout=15)

    def test_install_repeat_upgrade_and_preserve_user_state(self):
        for version in ('1.2.3', '1.2.3', '1.2.4'):
            if version == '1.2.4':
                self.publish(version)
            result = self.provision()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = self.run_claude('--version')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(version, result.stdout)
            self.assertEqual(self.run_claude('auth', 'status').returncode, 0)
            self.assert_state()
            self.assertTrue((self.home / '.claude/fixture-skills').exists())
        policy = json.loads((self.system / 'settings/managed-settings.json').read_text())
        self.assertEqual(policy['attribution'], {'commit': '', 'pr': ''})
        self.assertEqual(policy['env']['DISABLE_AUTOUPDATER'], '1')
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
            self.assertEqual(self.run_claude('--version', path=path, cwd=project).returncode, 0)
            self.assertEqual(self.run_claude('auth', 'status', path=path, cwd=project).returncode, 0)
            child = self.run_claude('fixture-child', path=path, cwd=project)
            self.assertEqual(child.returncode, 42 if selection == 'missing' else 0)
            if selection != 'missing':
                self.assertEqual(child.stdout.strip(), selection)

    @unittest.skipUnless(shutil.which('npm') and shutil.which('node'), 'npm is required for migration')
    def test_migrates_real_npm_packages_from_retained_node_prefixes(self):
        # A nested project/global prefix is not a Provisioning-owned install.
        unmanaged = (self.home / '.local/share/mise/installs/node/22.0.0'
                     / 'workspace/lib/node_modules/@anthropic-ai/claude-code')
        unmanaged.mkdir(parents=True)
        (unmanaged / 'package.json').write_text('{"name":"@anthropic-ai/claude-code"}')
        prefixes = []
        for version in ('22.0.0', '24.0.0'):
            prefix = self.home / '.local/share/mise/installs/node' / version
            package = prefix / 'lib/node_modules/@anthropic-ai/claude-code'
            package.mkdir(parents=True)
            (package / 'package.json').write_text(json.dumps({
                'name': '@anthropic-ai/claude-code', 'version': '0.0.0',
                'bin': {'claude': 'cli.js'}}))
            (package / 'cli.js').write_text('obsolete-distribution')
            (prefix / 'bin').mkdir()
            (prefix / 'bin/claude').symlink_to(package / 'cli.js')
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
        (self.home / '.local/bin/claude').symlink_to(prefixes[-1] / 'bin/claude')
        for _ in range(2):
            result = self.provision()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(self.run_claude('--version').returncode, 0)
            for prefix in prefixes:
                self.assertFalse((prefix / 'lib/node_modules/@anthropic-ai/claude-code').exists())
                self.assertFalse((prefix / 'bin/claude').is_symlink())
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
        self.assertIn('1.2.3', self.run_claude('--version').stdout)
        self.assert_state()
        (self.vendor / 'latest').write_text('<html>unavailable</html>')
        self.assertNotEqual(self.provision().returncode, 0)
        self.assertIn('1.2.3', self.run_claude('--version').stdout)
        self.assert_state()

    def test_unsupported_architecture_fails_without_installing(self):
        facts = {**self.variables['ansible_facts'], 'architecture': 'x86_64'}
        result = self.provision(ansible_facts=facts)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.system / 'bin/claude').exists())
        self.assert_state()
