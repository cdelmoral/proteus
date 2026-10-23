"""Execute the real AWS installation tasks with isolated paths and downloads."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile

from test_enroll import ROOT


@unittest.skipUnless(shutil.which('ansible-playbook'), 'Ansible is required')
class AWSProvisioningTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.home = self.directory / 'guest'
        self.home.mkdir()
        self.system = self.directory / 'system'
        (self.system / 'bin').mkdir(parents=True)
        self.credentials = self.home / '.aws/config'
        self.credentials.parent.mkdir()
        self.credentials.write_text('[default]\ncredential_process=preserve-enrollment\n')
        self.archive = self.directory / 'aws.zip'
        # Only the vendor installer boundary is simulated; get_url checksum,
        # extraction, command execution, and links are real Ansible operations.
        installer = '''#!/bin/sh
set -eu
[ "$1" = --install-dir ]
install_dir="$2"
[ "$3" = --bin-dir ]
bin_dir="$4"
mkdir -p "$install_dir/v2/2.38.5/bin"
printf '#!/bin/sh\\necho aws-cli/2.38.5\\n' > "$install_dir/v2/2.38.5/bin/aws"
chmod +x "$install_dir/v2/2.38.5/bin/aws"
ln -sf "$install_dir/v2/2.38.5/bin/aws" "$bin_dir/aws"
'''
        with zipfile.ZipFile(self.archive, 'w') as archive:
            info = zipfile.ZipInfo('aws/install')
            info.external_attr = 0o100755 << 16
            archive.writestr(info, installer)
        self.helper = self.directory / 'helper'
        self.helper.write_text('#!/bin/sh\necho roles-anywhere-fixture\n')
        self.tasks = self.directory / 'tasks.yml'
        self.tasks.write_text((ROOT / 'provisioning/tasks/aws.yml').read_text()
                              .replace('/usr/local', str(self.system))
                              .replace('become: true', 'become: false'))
        self.playbook = self.directory / 'playbook.yml'
        self.playbook.write_text(json.dumps([{
            'name': 'Exercise AWS Provisioning', 'hosts': 'all', 'gather_facts': False,
            'vars_files': [str(ROOT / 'provisioning/group_vars/all.yml')],
            'tasks': [{'ansible.builtin.import_tasks': str(self.tasks)}]}]))
        self.variables = {
            'ansible_facts': {'system': 'Linux', 'architecture': 'aarch64', 'user_dir': str(self.home)},
            'ansible_python_interpreter': os.sys.executable,
            'aws_cli_download_url': self.archive.as_uri(),
            'aws_cli_checksum': 'sha256:' + hashlib.sha256(self.archive.read_bytes()).hexdigest(),
            'aws_helper_download_url': self.helper.as_uri(),
            'aws_helper_checksum': 'sha256:' + hashlib.sha256(self.helper.read_bytes()).hexdigest(),
        }

    def provision(self, **variables):
        return subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local',
                               str(self.playbook), '-e', json.dumps({**self.variables, **variables})],
                              capture_output=True, text=True, timeout=60)

    def test_installs_executables_repeats_and_preserves_enrollment(self):
        for _ in range(2):
            result = self.provision()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for command, output in [('aws', 'aws-cli/2.38.5'), ('aws_signing_helper', 'roles-anywhere-fixture')]:
                result = subprocess.run([command], env={'PATH': str(self.system / 'bin')}, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout.strip(), output)
            self.assertEqual(self.credentials.read_text(), '[default]\ncredential_process=preserve-enrollment\n')

    def test_unsupported_architecture_and_bad_digest_prevent_installation(self):
        result = self.provision(ansible_facts={'system': 'Linux', 'architecture': 'x86_64', 'user_dir': str(self.home)})
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.system / 'bin/aws').exists())
        result = self.provision(aws_cli_checksum='sha256:' + '0' * 64)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.system / 'bin/aws').exists())
        self.assertEqual(self.credentials.read_text(), '[default]\ncredential_process=preserve-enrollment\n')
