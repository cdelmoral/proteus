"""Run real Salesforce Ansible tasks against a local archive/manifest boundary."""
import hashlib
import http.server
import io
import json
import os
import shutil
import subprocess
import tarfile
import unittest

from test_enroll import ROOT
from provisioning_fixture import prepare_playbook, provision, serve_vendor, temporary_guest


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        # Reproduce the observed vendor CDN rejection of Ansible's default UA.
        if self.headers.get('User-Agent') != 'curl':
            self.send_error(403)
            return
        super().do_GET()

    def log_message(self, *args):
        pass


@unittest.skipUnless(shutil.which('ansible-playbook'), 'Ansible is required')
class SalesforceProvisioningTest(unittest.TestCase):
    def setUp(self):
        temporary_guest(self)
        self.state = {'.sf/config.json': '{"target-dev-hub":"devhub"}',
                      '.sfdx/devhub.json': 'dummy-enrollment',
                      '.sfdx/key.json': 'dummy-file-keychain',
                      '.sf/plugins/package.json': '{"private":true}'}
        for name, content in self.state.items():
            path = self.home / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        launcher = self.home / '.local/bin/sf'
        launcher.parent.mkdir(parents=True)
        shutil.copy2(ROOT / 'dotfiles/home/.local/bin/sf', launcher)
        self.vendor = self.directory / 'vendor'
        self.vendor.mkdir()
        serve_vendor(self, QuietHandler)
        self.publish('1.2.3')
        prepare_playbook(self, 'salesforce', [])
        self.variables = {
            'ansible_facts': {'system': 'Linux', 'architecture': 'aarch64',
                              'user_dir': str(self.home), 'env': {'PATH': '/usr/bin:/bin'}},
            'ansible_python_interpreter': os.sys.executable,
            'salesforce_manifest_url': f'http://127.0.0.1:{self.server.server_port}/manifest',
        }

    def publish(self, version, bad_digest=False, broken=False):
        archive_path = self.vendor / (version + '.tar.xz')
        # Simulate only vendor files. Real tasks download, verify, extract,
        # invoke the runtime and activate the new release.
        files = {
            'sf/bin/node': f'#!{os.sys.executable}\nimport os,sys\nassert sys.argv[1] == "--no-deprecation"\nos.execv(sys.argv[2], sys.argv[2:])\n',
            'sf/bin/run.js': f'''#!{os.sys.executable}
import os, sys
assert os.environ['SF_USE_GENERIC_UNIX_KEYCHAIN'] == 'true'
assert os.environ['SF_DISABLE_TELEMETRY'] == 'true'
assert os.environ['SF_AUTOUPDATE_DISABLE'] == 'true'
assert os.environ['SF_DISABLE_AUTOUPDATE'] == 'true'
assert sys.argv[1:] == ['--version']  # Never enroll credentials.
print('@salesforce/cli/{version} fixture')
sys.exit({7 if broken else 0})
''',
        }
        with tarfile.open(archive_path, 'w:xz') as archive:
            for name, text in files.items():
                data = text.encode()
                entry = tarfile.TarInfo(name)
                entry.size, entry.mode = len(data), 0o755
                archive.addfile(entry, io.BytesIO(data))
        (self.vendor / 'manifest').write_text(json.dumps({
            'baseDir': 'sf', 'version': version, 'sha': 'abcdef',
            'xz': f'http://127.0.0.1:{self.server.server_port}/{archive_path.name}',
            'sha256xz': '0' * 64 if bad_digest else hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        }))

    def provision(self, **variables):
        return provision(self, **variables)

    def sf(self):
        return subprocess.run([str(self.home / '.local/bin/sf'), '--version'],
                              env={'HOME': str(self.home), 'PATH': '/usr/bin:/bin'},
                              capture_output=True, text=True, timeout=10)

    def assert_state(self):
        for name, content in self.state.items():
            self.assertEqual((self.home / name).read_text(), content)

    def test_install_repeat_and_update_preserve_state(self):
        for version in ('1.2.3', '1.2.3', '1.2.4'):
            if version == '1.2.4':
                self.publish(version)
            result = self.provision()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = self.sf()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(version, result.stdout)
            self.assert_state()

    def test_bad_archive_or_runtime_preserves_active_release(self):
        self.assertEqual(self.provision().returncode, 0)
        for bad_digest, broken in ((True, False), (False, True)):
            self.publish('1.2.4', bad_digest=bad_digest, broken=broken)
            self.assertNotEqual(self.provision().returncode, 0)
            self.assertEqual(self.sf().returncode, 0)
            self.assertIn('1.2.3', self.sf().stdout)
            self.assert_state()

    def test_unsupported_platform_fails(self):
        result = self.provision(ansible_facts={**self.variables['ansible_facts'], 'architecture': 'x86_64'})
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.home / '.local/share/proteus/salesforce-cli/current').exists())
        self.assert_state()
