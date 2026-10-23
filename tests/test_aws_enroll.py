"""Public host/guest command tests; no AWS or 1Password requests escape fixtures."""
import configparser
import json
import os
from pathlib import Path
import shutil
import subprocess

from test_enroll import EnrollmentHarness, ROOT


ACCOUNT = '123456789012'
ROLE = f'arn:aws:iam::{ACCOUNT}:role/development/Proteus'
VALUES = [ACCOUNT, ROLE, 'us-east-1',
          f'arn:aws:rolesanywhere:us-east-1:{ACCOUNT}:trust-anchor/12345678-1234-1234-1234-123456789abc',
          f'arn:aws:rolesanywhere:us-east-1:{ACCOUNT}:profile/12345678-1234-1234-1234-123456789abc',
          'op://workload/aws/certificate', 'op://workload/aws/private key']
KEYS = ['account_id', 'role_arn', 'region', 'trust_anchor_arn', 'profile_arn',
        'certificate_ref', 'private_key_ref']


class AWSEnrollmentTest(EnrollmentHarness):
    def setUp(self):
        super().setUp()
        self.configuration = Path(self.environment['XDG_CONFIG_HOME']) / 'proteus/config'
        self.configuration.parent.mkdir(parents=True)
        self.configuration.write_text('proteus_aws_enabled=true\n' + ''.join(
            f'proteus_aws_{k}={v}\n' for k, v in zip(KEYS, VALUES)))
        self.fixture = self.directory / 'fixture'
        self.fixture.mkdir()
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                        '-keyout', str(self.fixture / 'key'), '-out', str(self.fixture / 'cert'),
                        '-days', '365', '-subj', '/CN=proteus'], check=True, capture_output=True)
        self.certificate = (self.fixture / 'cert').read_text()
        self.private_key = (self.fixture / 'key').read_text()
        self.environment.update(TEST_CERT=self.certificate, TEST_KEY=self.private_key)
        # Relocate only installation paths in the real public entrypoints. This
        # keeps the fixture off /usr/local while executing their actual logic.
        self.system = self.directory / 'system-bin'
        self.system.mkdir()
        self.host = self.directory / 'host-command'
        self.host.mkdir()
        shutil.copytree(ROOT / 'lib', self.host / 'lib')
        self.entrypoint = self.host / 'enroll'
        self.entrypoint.write_text((ROOT / 'enroll').read_text().replace('/usr/local/bin', str(self.system)))
        self.entrypoint.chmod(0o755)
        helper = self.guest / '.local/bin/proteus-enroll-aws'
        helper.write_text((ROOT / 'dotfiles/home/.local/bin/proteus-enroll-aws').read_text().replace('/usr/local/bin', str(self.system)))
        helper.chmod(0o755)
        self.write_command(self.bin / 'op', '''
import json, os, sys
with open(os.environ['TEST_LOG'], 'a') as log:
    log.write(json.dumps(['op'] + sys.argv[1:]) + '\\n')
assert sys.argv[1] == 'read'
assert sys.argv[2] in ('op://workload/aws/certificate', 'op://workload/aws/private key')
if os.environ.get('TEST_READ_FAIL') and 'private key' in sys.argv[2]:
    print(os.environ['TEST_KEY'], file=sys.stderr)
    sys.exit(1)
print(os.environ['TEST_KEY'] if 'private key' in sys.argv[2] else os.environ['TEST_CERT'])
''')
        self.write_command(self.system / 'aws_signing_helper', '''
import json, os, pathlib, sys
if os.environ.get('TEST_HELPER_FAIL'):
    print(os.environ['TEST_KEY'], file=sys.stderr)
    sys.exit(1)
assert sys.argv[1] == 'credential-process'
assert pathlib.Path(sys.argv[sys.argv.index('--certificate')+1]).read_text().strip() == os.environ['TEST_CERT'].strip()
assert pathlib.Path(sys.argv[sys.argv.index('--private-key')+1]).read_text().strip() == os.environ['TEST_KEY'].strip()
print(json.dumps({'Version': 1, 'AccessKeyId': 'candidate-only', 'SecretAccessKey': 'fixture', 'SessionToken': 'fixture'}))
''')
        self.write_command(self.system / 'aws', '''
import configparser, json, os, pathlib, shlex, subprocess, sys
# Model the external AWS provider chain at the command boundary. No exported
# credentials or profile may substitute for the candidate's credential_process.
for key in ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN',
            'AWS_PROFILE', 'AWS_DEFAULT_PROFILE', 'AWS_ENDPOINT_URL', 'AWS_WEB_IDENTITY_TOKEN_FILE'):
    assert key not in os.environ
assert os.environ['AWS_EC2_METADATA_DISABLED'] == 'true'
c = configparser.RawConfigParser()
c.read(os.environ.get('AWS_CONFIG_FILE', str(pathlib.Path.home() / '.aws/config')))
result = subprocess.run(shlex.split(c['default']['credential_process']), capture_output=True)
if result.returncode: sys.exit(1)
assert json.loads(result.stdout)['AccessKeyId'] == 'candidate-only'
if os.environ.get('TEST_STS_FAIL'):
    print(os.environ['TEST_KEY'], file=sys.stderr)
    sys.exit(1)
print(json.dumps({'Account': os.environ.get('TEST_ACCOUNT', '123456789012'),
    'Arn': os.environ.get('TEST_ARN', 'arn:aws:sts::123456789012:assumed-role/Proteus/session')}))
''')

    def enroll(self, instance=None, **env):
        result = subprocess.run([str(self.entrypoint), 'aws'] + ([instance] if instance else []),
                                env={**self.environment, **env}, capture_output=True, text=True, timeout=15)
        self.assertNotIn(self.private_key.strip(), result.stdout + result.stderr)
        self.assertNotIn(self.certificate.strip(), result.stdout + result.stderr)
        for call in self.calls():
            self.assertNotIn(self.private_key.strip(), json.dumps(call))
        return result

    def test_enroll_rotate_and_noninteractive_default_profile(self):
        aws = self.guest / '.aws'
        aws.mkdir()
        (aws / 'config').write_text('[profile other]\nregion=eu-west-1\n[default]\noutput=yaml\n')
        (aws / 'credentials').write_text('[other]\naws_access_key_id=keep\n')
        before = (aws / 'credentials').read_bytes()
        for _ in range(2):
            result = self.enroll('custom-instance', AWS_ACCESS_KEY_ID='ambient', AWS_SECRET_ACCESS_KEY='ambient',
                                 AWS_PROFILE='other', AWS_ENDPOINT_URL='https://invalid', AWS_WEB_IDENTITY_TOKEN_FILE='/bad')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((aws / 'credentials').read_bytes(), before)
            c = configparser.RawConfigParser()
            c.read(aws / 'config')
            self.assertEqual(c['profile other']['region'], 'eu-west-1')
            self.assertEqual(c['default']['output'], 'yaml')
            self.assertEqual((aws / 'config').stat().st_mode & 0o777, 0o600)
            for path in (self.guest / '.local/share/proteus/aws').rglob('*'):
                self.assertEqual(path.stat().st_mode & 0o077, 0)
            # Same default-provider use as a background T3 subprocess; no shell,
            # exported access keys, or T3 service interaction.
            env = {**self.environment, 'HOME': str(self.guest),
                   'AWS_EC2_METADATA_DISABLED': 'true'}
            result = subprocess.run([str(self.system / 'aws'), 'sts', 'get-caller-identity'], env=env,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(all(call[0] in ('list', 'shell', 'op') for call in self.calls()))
        shell_calls = [call for call in self.calls() if call[0] == 'shell']
        self.assertTrue(all('--start=false' in call and 'custom-instance' in call for call in shell_calls))

    def test_guest_home_with_spaces_uses_quoted_credential_paths(self):
        renamed = self.directory / 'guest with spaces'
        self.guest.rename(renamed)
        self.guest = renamed
        self.environment['TEST_GUEST'] = str(renamed)
        result = self.enroll()
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([str(self.system / 'aws'), 'sts', 'get-caller-identity'],
                                env={**self.environment, 'HOME': str(self.guest),
                                     'AWS_EC2_METADATA_DISABLED': 'true'}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_failed_candidates_preserve_working_config_and_pair(self):
        self.assertEqual(self.enroll().returncode, 0)
        config_path = self.guest / '.aws/config'
        previous = config_path.read_bytes()
        generations = sorted((self.guest / '.local/share/proteus/aws').iterdir())
        for env in ({'TEST_READ_FAIL': '1'}, {'TEST_CERT': 'bad certificate'},
                    {'TEST_KEY': 'bad key'}, {'TEST_HELPER_FAIL': '1'}, {'TEST_STS_FAIL': '1'},
                    {'TEST_ACCOUNT': '999999999999'},
                    {'TEST_ARN': 'arn:aws:sts::123456789012:assumed-role/ProteusExtra/session'},
                    {'TEST_ARN': 'arn:aws:sts::123456789012:assumed-role/Other/session'}):
            with self.subTest(env=list(env)):
                result = self.enroll(**env)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertNotIn('Enrolled AWS', result.stdout)
                self.assertEqual(config_path.read_bytes(), previous)
                self.assertEqual(sorted((self.guest / '.local/share/proteus/aws').iterdir()), generations)

    def test_resolution_finishes_before_transfer_and_failure_transfers_nothing(self):
        result = self.enroll(TEST_READ_FAIL='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len([c for c in self.calls() if c[0] == 'shell']), 1)
        self.log.unlink()
        self.assertEqual(self.enroll().returncode, 0)
        calls = self.calls()
        self.assertEqual([c[0] for c in calls], ['list', 'shell', 'op', 'op', 'shell'])

    def test_prerequisites_rejected_before_secret_resolution(self):
        for status in ('', 'Stopped'):
            with self.subTest(status=status):
                self.log.unlink(missing_ok=True)
                self.assertNotEqual(self.enroll(TEST_VM_STATUS=status).returncode, 0)
                self.assertFalse(any(c[0] == 'op' for c in self.calls()))
        (self.system / 'aws_signing_helper').unlink()
        self.log.unlink()
        self.assertNotEqual(self.enroll().returncode, 0)
        self.assertFalse(any(c[0] == 'op' for c in self.calls()))

    def test_missing_disabled_and_inconsistent_configuration(self):
        original = self.configuration.read_text()
        for value in ('', original.replace('=true', '=false'),
                      original.replace('us-east-1:123456789012:profile', 'us-west-2:123456789012:profile')):
            self.configuration.write_text(value)
            self.assertNotEqual(self.enroll().returncode, 0)
            self.assertEqual(self.calls(), [])

    def test_real_mismatched_and_expired_certificates_are_rejected(self):
        self.assertEqual(self.enroll().returncode, 0)
        config_path = self.guest / '.aws/config'
        previous = config_path.read_bytes()
        subprocess.run(['openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:2048',
                        '-out', str(self.fixture / 'other-key')], check=True, capture_output=True)
        result = self.enroll(TEST_KEY=(self.fixture / 'other-key').read_text())
        self.assertNotEqual(result.returncode, 0)
        (self.fixture / 'index').touch()
        (self.fixture / 'serial').write_text('01\n')
        ca_config = self.fixture / 'ca.conf'
        ca_config.write_text(f'[ca]\ndefault_ca=local\n[local]\n'
                             f'database={self.fixture}/index\nserial={self.fixture}/serial\n'
                             f'new_certs_dir={self.fixture}\ndefault_md=sha256\npolicy=policy\nunique_subject=no\n'
                             '[policy]\ncommonName=supplied\n')
        subprocess.run(['openssl', 'x509', '-x509toreq', '-in', str(self.fixture / 'cert'),
                        '-signkey', str(self.fixture / 'key'), '-out', str(self.fixture / 'request')],
                       check=True, capture_output=True)
        for start, end in [('20200101000000Z', '20210101000000Z'),
                           ('20990101000000Z', '21000101000000Z')]:
            subprocess.run(['openssl', 'ca', '-selfsign', '-batch', '-notext', '-config', str(ca_config),
                            '-keyfile', str(self.fixture / 'key'), '-cert', str(self.fixture / 'cert'),
                            '-in', str(self.fixture / 'request'), '-out', str(self.fixture / 'dated'),
                            '-startdate', start, '-enddate', end], check=True, capture_output=True)
            result = self.enroll(TEST_CERT=(self.fixture / 'dated').read_text())
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('currently valid', result.stderr)
        self.assertEqual(config_path.read_bytes(), previous)

    def test_interrupted_transfer_preserves_previous_setup(self):
        self.assertEqual(self.enroll().returncode, 0)
        config_path = self.guest / '.aws/config'
        previous = config_path.read_bytes()
        helper = self.guest / '.local/bin/proteus-enroll-aws'
        result = subprocess.run([str(helper)], input=b'incomplete', capture_output=True,
                                env={**self.environment, 'HOME': str(self.guest)})
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(config_path.read_bytes(), previous)

    def test_default_static_credentials_cannot_override_enrollment(self):
        aws = self.guest / '.aws'
        aws.mkdir()
        (aws / 'credentials').write_text('[default]\naws_access_key_id=ambient\n')
        self.assertNotEqual(self.enroll().returncode, 0)
        self.assertFalse((aws / 'config').exists())
