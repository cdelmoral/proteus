"""Integrated public setup -> configure -> enroll lifecycle, with local X.509.

Reuse command fixtures; services are simulated, not real acceptance evidence.
"""
import configparser
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import unittest

import test_aws_setup as host_fixture
import test_aws_enroll as guest_fixture


class AWSLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.host = host_fixture.AWSSetupTest()
        self.addCleanup(self.host.doCleanups)
        self.host.setUp()
        self.guest = guest_fixture.AWSEnrollmentTest()
        self.addCleanup(self.guest.doCleanups)
        self.guest.setUp()
        self.guest.environment['FAKE_STATE'] = str(self.host.state_path)
        self.guest.write_command(self.guest.bin / 'op', '''
import json, os, sys
assert sys.argv[1] == 'read'
vault, item, field = sys.argv[2][5:].split('/')
assert vault == 'work'  # Enrollment must never resolve the protected CA.
state = json.load(open(os.environ['FAKE_STATE']))
document = next(d for d in state['vaults'][vault] if d['id'] == item)
print(next(f['value'] for f in document['fields'] if f['label'] == field))
''')
        # No ambient AWS values in ordinary default-profile use.
        for key in list(self.guest.environment):
            if key.startswith('AWS_'):
                del self.guest.environment[key]

    def configure(self, output):
        settings = dict((key, json.loads(value)) for key, value in
                        (line.split(': ', 1) for line in output.splitlines()
                         if line.startswith('proteus_aws_')))
        answers = 'op://github/token/value\nop://github/signing/value\n\ntrue\n'
        answers += '\n'.join(settings['proteus_aws_' + key] for key in guest_fixture.KEYS) + '\n'
        result = subprocess.run([str(host_fixture.ROOT / 'configure')], input=answers,
                                env=self.guest.environment, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('proteus_aws_enabled=true\n', self.guest.configuration.read_text())
        self.assertNotIn('proteus_aws_enabled:', self.guest.configuration.read_text())
        self.sync_pair()

    def sync_pair(self):
        pair = self.host.pair('work')
        self.guest.environment.update(TEST_CERT=pair['certificate'], TEST_KEY=pair['private key'],
                                      TEST_ARN='arn:aws:sts::123456789012:assumed-role/proteus/session')

    def enroll(self, **env):
        self.sync_pair()
        return self.guest.enroll(**env)

    def active(self):
        config = self.guest.guest / '.aws/config'
        parser = configparser.RawConfigParser()
        parser.read(config)
        command = shlex.split(parser['default']['credential_process'])
        return (config.read_bytes(),
                Path(command[command.index('--certificate') + 1]).read_bytes(),
                Path(command[command.index('--private-key') + 1]).read_bytes())

    def assert_usable(self):
        result = subprocess.run([str(self.guest.system / 'aws'), 'sts', 'get-caller-identity'],
                                env={**self.guest.environment, 'HOME': str(self.guest.guest),
                                     'AWS_EC2_METADATA_DISABLED': 'true'},
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['Account'], host_fixture.ACCOUNT)

    def initial(self):
        self.configure(self.host.setup().stdout)
        self.assertEqual(self.enroll().returncode, 0)
        self.assert_usable()

    def renew(self, **kwargs):
        offset = len(self.host.requests())
        result = self.host.setup(host_fixture.REFERENCES + 'yes\n', renew=True, **kwargs)
        self.assertFalse(any(arg.startswith(('create-', 'attach-', 'update-', 'delete-'))
                             for tool, args in self.host.requests()[offset:] if tool == 'aws' for arg in args))
        return result

    def test_annual_replacement_failed_enrollment_and_fresh_guest(self):
        self.initial()
        before = self.host.state()
        active = self.active()
        output = self.renew().stdout
        after = self.host.state()
        self.assertEqual(before['vaults']['protected'], after['vaults']['protected'])
        for resource in ('trustAnchors', 'Roles', 'profiles', 'attached'):
            self.assertEqual(before[resource], after[resource])
        self.assertNotEqual(self.host.pair('work')['certificate'].encode(), active[1])
        self.assertNotEqual(self.host.pair('work')['private key'].encode(), active[2])
        self.assertEqual(self.active(), active)  # Issuance never activates the guest.
        self.configure(output)
        self.assertNotEqual(self.enroll(TEST_HELPER_FAIL='1').returncode, 0)
        self.assertEqual(self.active(), active)
        # Previous guest pair remains usable after candidate verification fails.
        self.guest.environment.update(TEST_CERT=active[1].decode(), TEST_KEY=active[2].decode())
        self.assert_usable()
        self.assertEqual(self.enroll().returncode, 0)
        self.assertNotEqual(self.active(), active)
        self.assert_usable()
        renewed = self.active()
        # Simulate a rebuilt guest's empty enrollment state, retaining installed
        # helper/tools. Provisioning itself is exercised by its own task tests.
        shutil.rmtree(self.guest.guest / '.aws')
        shutil.rmtree(self.guest.guest / '.local/share/proteus/aws')
        self.assertEqual(self.enroll().returncode, 0)
        self.assertEqual(self.active()[1:], renewed[1:])
        self.assert_usable()
        self.assertEqual(self.host.state(), after)
        self.assertTrue(all(c[0] in ('list', 'shell') for c in self.guest.calls()))

    def test_failed_issuance_storage_verification_or_decline_preserves_pair_and_guest(self):
        self.initial()
        active = self.active()
        before = self.host.state()
        real_openssl = shutil.which('openssl')
        openssl = self.host.bin / 'openssl'
        openssl.write_text('#!/usr/bin/env python3\nimport os, sys\n'
                           'if sys.argv[1:3] == ["x509", "-req"]: sys.exit(1)\n'
                           f'os.execv({real_openssl!r}, [{real_openssl!r}] + sys.argv[1:])\n')
        openssl.chmod(0o755)
        self.renew(success=False)
        openssl.unlink()
        self.assertEqual(self.host.state(), before)
        for changes in ({'op_failure': 'edit'}, {'helper_failure': True},
                        {'workload_account': '999999999999'}):
            with self.subTest(changes=changes):
                self.host.change(**changes)
                selected = self.host.state()
                self.renew(success=False)
                self.assertEqual(self.host.state(), selected)
                self.assertEqual(self.active(), active)
                self.host.state_path.write_text(json.dumps(before))
        self.host.setup(host_fixture.REFERENCES + 'no\n', renew=True, success=False)
        self.assertEqual(self.host.state(), before)
        self.assertEqual(self.active(), active)
        self.assert_usable()

    def test_renewal_never_creates_missing_ca_or_resources(self):
        self.initial()
        before = self.host.state()
        for missing in ('ca', 'trustAnchors', 'Roles', 'profiles'):
            with self.subTest(missing=missing):
                state = json.loads(json.dumps(before))
                if missing == 'ca':
                    state['vaults']['protected'] = []
                else:
                    state[missing] = []
                self.host.change(**state)
                offset = len(self.host.requests())
                self.renew(success=False)
                self.assertEqual(self.host.state(), state)
                calls = self.host.requests()[offset:]
                self.assertFalse(any(arg.startswith(('create-', 'attach-', 'update-'))
                                     for tool, args in calls if tool == 'aws' for arg in args))
                self.assertFalse(any(args[1] in ('create', 'edit') for tool, args in calls if tool == 'op'))
        self.host.change(**before)

    def test_expiration_recovery_uses_original_ca_and_trust(self):
        self.initial()
        before = self.host.state()
        fixture = self.host.home / 'dated'
        fixture.mkdir()
        ca = self.host.pair('protected')
        pair = self.host.pair('work')
        for name, value in (('ca.pem', ca['certificate']), ('ca.key', ca['private key']),
                            ('key', pair['private key']), ('cert', pair['certificate'])):
            (fixture / name).write_text(value)
        (fixture / 'index').touch()
        (fixture / 'serial').write_text('01\n')
        config = fixture / 'ca.conf'
        config.write_text(f'[ca]\ndefault_ca=local\n[local]\ndatabase={fixture}/index\n'
                          f'serial={fixture}/serial\nnew_certs_dir={fixture}\n'
                          'default_md=sha256\npolicy=policy\nx509_extensions=workload\n'
                          '[policy]\ncommonName=supplied\n[workload]\nbasicConstraints=critical,CA:FALSE\n'
                          'keyUsage=critical,digitalSignature\n')
        def openssl(*args):
            subprocess.run(['openssl', *map(str, args)], check=True, capture_output=True)
        openssl('x509', '-x509toreq', '-in', fixture / 'cert', '-signkey', fixture / 'key', '-out', fixture / 'csr')
        openssl('ca', '-batch', '-notext', '-config', config, '-keyfile', fixture / 'ca.key',
                '-cert', fixture / 'ca.pem', '-in', fixture / 'csr', '-out', fixture / 'expired',
                '-startdate', '20200101000000Z', '-enddate', '20210101000000Z')
        state = self.host.state()
        for field in state['vaults']['work'][0]['fields']:
            if field['label'] == 'certificate':
                field['value'] = (fixture / 'expired').read_text()
        self.host.change(**state)
        active = self.active()
        result = self.enroll()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('currently valid', result.stderr)
        self.assertEqual(self.active(), active)
        result = self.host.setup(host_fixture.REFERENCES, success=False)
        self.assertIn("--renew", result.stderr)
        self.renew()
        self.assertEqual(self.enroll().returncode, 0)
        self.assert_usable()
        after = self.host.state()
        self.assertEqual(before['vaults']['protected'], after['vaults']['protected'])
        for resource in ('trustAnchors', 'Roles', 'profiles'):
            self.assertEqual(before[resource], after[resource])

    def test_uncertain_vault_write_requires_inspection_and_preserves_guest(self):
        self.initial()
        active = self.active()
        old = self.host.pair('work')
        self.host.change(op_failure_after_edit=True)
        result = self.renew(success=False)
        self.assertIn('inspect both workload fields', result.stderr)
        self.assertNotEqual(self.host.pair('work'), old)
        self.assertEqual(self.active(), active)
        self.assert_usable()
        # A completed write can be recovered without rotating again.
        self.host.change(op_failure_after_edit=False, op_failure=None)
        self.host.setup(host_fixture.REFERENCES)
        self.assertEqual(self.enroll().returncode, 0)
        self.assert_usable()

    def test_invalid_old_pair_or_changed_trust_cannot_be_renewed(self):
        self.initial()
        before = self.host.state()
        active = self.active()
        for defect in ('key', 'certificate', 'anchor', 'role', 'profile'):
            with self.subTest(defect=defect):
                state = json.loads(json.dumps(before))
                if defect in ('key', 'certificate'):
                    for field in state['vaults']['work'][0]['fields']:
                        if field['label'] == ('private key' if defect == 'key' else 'certificate'):
                            field['value'] = self.host.pair('protected')[field['label']]
                elif defect == 'anchor':
                    state['trustAnchors'][0]['enabled'] = False
                elif defect == 'role':
                    state['Roles'][0]['AssumeRolePolicyDocument'] = {}
                else:
                    state['profiles'][0]['enabled'] = False
                self.host.state_path.write_text(json.dumps(state))
                self.renew(success=False)
                self.assertEqual(self.host.state(), state)
                self.assertEqual(self.active(), active)
                self.host.state_path.write_text(json.dumps(before))
