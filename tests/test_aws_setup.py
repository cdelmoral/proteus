"""Run the public host command with real OpenSSL and simulated AWS/1Password."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
ACCOUNT = "123456789012"
COMMAND = [str(ROOT / "aws-setup"), "--account-id", ACCOUNT,
           "--admin-profile", "human-admin", "--region", "us-east-1"]
REFERENCES = "yes\nop://work/Workload/certificate\nop://protected/CA/certificate\n"

# The simulated tools persist state and reject unknown commands. Arguments and
# non-secret requests are logged; secret stdin is stored only in simulated vaults.
FAKE = r'''#!/usr/bin/env python3
import configparser
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

home = Path(os.environ['FAKE_HOME'])
state_file = home / 'state.json'
state = json.loads(state_file.read_text())
args = sys.argv[1:]
tool = Path(sys.argv[0]).name
with (home / 'requests.jsonl').open('a') as log:
    log.write(json.dumps([tool, args]) + '\n')
def done(value):
    state_file.write_text(json.dumps(state))
    if value is not None:
        print(json.dumps(value))
    sys.exit(0)
def fail():
    print('EXTERNAL-SECRET-DIAGNOSTIC -----BEGIN PRIVATE KEY-----', file=sys.stderr)
    sys.exit(1)
def option(name):
    return args[args.index('--' + name) + 1]
if tool == 'aws_signing_helper':
    assert args[0] == 'credential-process'
    assert not any(k in os.environ for k in ('AWS_ACCESS_KEY_ID', 'AWS_PROFILE', 'AWS_ENDPOINT_URL'))
    cert, key = Path(option('certificate')), Path(option('private-key'))
    assert cert.exists() and key.exists()
    assert cert.stat().st_mode & 0o777 == 0o600
    assert cert.parent.stat().st_mode & 0o777 == 0o700
    if state.get('helper_failure'):
        fail()
    done({'Version': 1, 'AccessKeyId': 'dummy', 'SecretAccessKey': 'dummy', 'SessionToken': 'dummy'})
if tool == 'op':
    assert args[0] == 'item'
    operation = args[1]
    vault = option('vault')
    if state.get('op_failure') == operation:
        fail()
    items = state['vaults'].setdefault(vault, [])
    if operation == 'list':
        done([{'id': i['id'], 'title': i['title'], 'state': i.get('state', 'ACTIVE')} for i in items])
    if operation == 'get':
        done(next(i for i in items if i['id'] == args[2]))
    if operation in ('create', 'edit'):
        document = json.load(sys.stdin)
        if operation == 'create':
            assert args[-1] == '-'
            document['id'] = 'item' + str(len(items) + 1)
            document['vault'] = {'id': vault}
            assert not any(i['title'] == document['title'] for i in items)
            items.append(document)
        else:
            assert args[2] == document['id']
            items[:] = [document if i['id'] == document['id'] else i for i in items]
        done(document)
    raise AssertionError(args)
if tool == 'aws':
    service = next(s for s in ('sts', 'iam', 'rolesanywhere') if s in args)
    index = args.index(service)
    operation = args[index + 1]
    admin = '--profile' in args
    if admin:
        assert option('profile') == 'human-admin'
        assert 'AWS_ACCESS_KEY_ID' not in os.environ
        assert 'AWS_ENDPOINT_URL' not in os.environ
    if state.get('aws_failure') == operation:
        fail()
    if state.get('aws_empty_output') == operation:
        done(None)
    if service == 'sts':
        assert operation == 'get-caller-identity'
        if admin:
            done({'Account': state.get('admin_account', '123456789012')})
        config = configparser.RawConfigParser()
        config.read(os.environ['AWS_CONFIG_FILE'])
        assert Path(os.environ['AWS_SHARED_CREDENTIALS_FILE']).read_text() == ''
        result = subprocess.run(shlex.split(config['default']['credential_process']), capture_output=True)
        if result.returncode:
            fail()
        done({'Account': state.get('workload_account', '123456789012'),
              'Arn': state.get('workload_arn', 'arn:aws:sts::123456789012:assumed-role/proteus/session')})
    if operation.startswith('list-'):
        collection = {'list-trust-anchors': 'trustAnchors', 'list-roles': 'Roles', 'list-profiles': 'profiles'}[operation]
        done({collection: state.get(collection, [])})
    if operation == 'create-trust-anchor':
        value = {'name': option('name'), 'source': json.loads(option('source')), 'enabled': True,
                 'trustAnchorArn': 'arn:aws:rolesanywhere:us-east-1:123456789012:trust-anchor/anchor1'}
        state['trustAnchors'] = [value]
        done({'trustAnchor': value})
    if operation == 'create-role':
        value = {'RoleName': option('role-name'), 'Arn': 'arn:aws:iam::123456789012:role/proteus',
                 'AssumeRolePolicyDocument': json.loads(option('assume-role-policy-document'))}
        state['Roles'] = [value]
        done({'Role': value})
    if operation == 'attach-role-policy':
        assert option('policy-arn') == 'arn:aws:iam::aws:policy/AdministratorAccess'
        state['attached'] = True
        done(None)
    if operation == 'create-profile':
        value = {'name': option('name'), 'profileId': 'profile1', 'roleArns': json.loads(option('role-arns')),
                 'enabled': True, 'profileArn': 'arn:aws:rolesanywhere:us-east-1:123456789012:profile/profile1'}
        state['profiles'] = [value]
        done({'profile': value})
    if operation == 'get-profile':
        done({'profile': state['profiles'][0]})
    raise AssertionError(args)
raise AssertionError(tool)
'''


class AWSSetupTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.bin = self.home / "bin"
        self.bin.mkdir()
        (self.home / "tmp").mkdir()
        self.state_path = self.home / "state.json"
        self.state_path.write_text(json.dumps({"vaults": {}}))
        for tool in ("aws", "op", "aws_signing_helper"):
            path = self.bin / tool
            path.write_text(FAKE)
            path.chmod(0o755)
        self.environment = {**os.environ, "HOME": str(self.home), "FAKE_HOME": str(self.home),
                            "TMPDIR": str(self.home / "tmp"), "PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
                            "AWS_ACCESS_KEY_ID": "ambient-must-not-pass", "AWS_PROFILE": "production",
                            "AWS_ENDPOINT_URL": "https://must-not-pass.invalid"}

    def state(self):
        return json.loads(self.state_path.read_text())

    def change(self, **changes):
        state = self.state()
        state.update(changes)
        self.state_path.write_text(json.dumps(state))

    def requests(self):
        path = self.home / "requests.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def setup(self, responses=REFERENCES + "yes\nyes\n", success=True):
        result = subprocess.run(COMMAND, input=responses, capture_output=True, text=True,
                                env=self.environment, timeout=30)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("proteus_aws_enabled:", result.stdout)
        output = result.stdout + result.stderr
        self.assertNotIn("PRIVATE KEY", output)
        self.assertNotIn("EXTERNAL-SECRET", output)
        self.assertNotIn("PRIVATE KEY", json.dumps(self.requests()))
        self.assertEqual(list((self.home / "tmp").iterdir()), [])
        return result

    def pair(self, vault):
        item = self.state()["vaults"][vault][0]
        return {field["label"]: field.get("value", "") for field in item["fields"]}

    def assert_no_cloud_mutations(self):
        for tool, args in self.requests():
            if tool == "aws":
                self.assertFalse(any(arg.startswith(("create-", "attach-", "update-", "delete-")) for arg in args))

    def test_account_mismatch_makes_no_changes_or_vault_access(self):
        self.change(admin_account="999999999999")
        result = self.setup("", success=False)
        self.assertIn("account mismatch", result.stderr)
        self.assertEqual(len(self.requests()), 1)
        self.assert_no_cloud_mutations()

    def test_creates_valid_separate_pairs_constrained_trust_and_verified_output(self):
        result = self.setup()
        self.assertLess(result.stdout.index("Workload certificate reference"), result.stdout.index("Create selected workload"))
        workload, ca = self.pair("work"), self.pair("protected")
        self.assertNotEqual(ca["private key"], workload["private key"])
        self.assertNotIn(ca["private key"], json.dumps(self.state()["vaults"]["work"]))
        for key in ("proteus_aws_account_id", "proteus_aws_role_arn", "proteus_aws_region",
                    "proteus_aws_trust_anchor_arn", "proteus_aws_profile_arn",
                    "proteus_aws_certificate_ref", "proteus_aws_private_key_ref"):
            self.assertIn(key + ":", result.stdout)
        self.assertIn('"op://work/item1/private key"', result.stdout)
        certificate = self.home / "certificate.pem"
        certificate.write_text(workload["certificate"])
        dates = subprocess.check_output(["openssl", "x509", "-in", str(certificate), "-noout", "-dates"], text=True)
        start, end = [datetime.datetime.strptime(line.split("=", 1)[1], "%b %d %H:%M:%S %Y %Z")
                      for line in dates.splitlines()]
        self.assertEqual(end - start, datetime.timedelta(days=365))
        text = subprocess.check_output(["openssl", "x509", "-in", str(certificate), "-text", "-noout"], text=True)
        self.assertIn("CA:FALSE", text)
        self.assertIn("Digital Signature", text)
        trust = self.state()["Roles"][0]["AssumeRolePolicyDocument"]["Statement"][0]
        self.assertEqual(set(trust["Action"]), {"sts:AssumeRole", "sts:TagSession", "sts:SetSourceIdentity"})
        self.assertEqual(trust["Condition"]["StringEquals"]["aws:PrincipalTag/x509Subject/CN"], "proteus")
        self.assertIn("anchor1", trust["Condition"]["ArnEquals"]["aws:SourceArn"])
        requests = self.requests()
        self.assertIn("get-caller-identity", requests[0][1])
        self.assertTrue(any(tool == "aws_signing_helper" for tool, _ in requests))
        self.assertFalse((self.home / ".aws").exists())
        self.assertFalse((self.home / ".config/proteus").exists())

    def test_declined_workload_storage_or_ca_creation_has_no_mutations(self):
        for responses in (REFERENCES + "no\n", REFERENCES + "yes\nno\n"):
            with self.subTest(responses=responses):
                self.setup(responses, success=False)
                self.assert_no_cloud_mutations()
                self.assertFalse(any(args[1] in ("create", "edit") for tool, args in self.requests() if tool == "op"))

    def test_incomplete_existing_workload_item_is_updated_preserving_unrelated_fields(self):
        document = {"id": "existing", "title": "Workload", "vault": {"id": "work"}, "category": "SECURE_NOTE",
                    "fields": [{"id": "notesPlain", "label": "notesPlain", "value": "keep-me", "type": "STRING"}]}
        self.change(vaults={"work": [document]})
        result = self.setup()
        self.assertIn("Update selected workload", result.stdout)
        self.assertEqual(self.pair("work")["notesPlain"], "keep-me")
        self.assertTrue(any(tool == "op" and args[1] == "edit" for tool, args in self.requests()))

    def test_retry_reuses_ca_pair_and_existing_resources(self):
        self.setup()
        before = self.state()
        offset = len(self.requests())
        self.setup(REFERENCES)
        self.assertEqual(self.state(), before)
        repeated = self.requests()[offset:]
        self.assertFalse(any("create" in args or any(a.startswith("create-") for a in args) for _, args in repeated))
        self.assertFalse(any(tool == "op" and args[1] == "edit" for tool, args in repeated))

    def test_partial_cloud_failure_can_retry_without_ca_or_workload_rotation(self):
        self.change(aws_failure="create-role")
        self.setup(success=False)
        pairs = self.state()["vaults"]
        self.assertTrue(self.state()["trustAnchors"])
        self.change(aws_failure=None)
        self.setup(REFERENCES)
        self.assertEqual(self.state()["vaults"], pairs)

    def test_failed_policy_attachment_is_secret_free_and_retry_reuses_pairs(self):
        self.change(aws_failure="attach-role-policy")
        result = self.setup(success=False)
        self.assertIn("AWS iam attach-role-policy failed", result.stderr)
        self.assertNotIn("Setup complete", result.stdout)
        before = self.state()
        self.assertNotIn("profiles", before)
        self.assertFalse(any(tool == "aws_signing_helper" for tool, _ in self.requests()))
        self.change(aws_failure=None)
        self.setup(REFERENCES)
        self.assertEqual(self.state()["vaults"], before["vaults"])
        self.assertEqual(self.state()["Roles"], before["Roles"])
        self.assertTrue(self.state()["attached"])
        self.assertTrue(self.state()["profiles"])

    def test_empty_output_for_json_operation_fails_without_complete_output(self):
        self.change(aws_empty_output="list-profiles")
        result = self.setup(success=False)
        self.assertIn("invalid JSON", result.stderr)
        self.assertNotIn("Setup complete", result.stdout)
        self.assertNotIn("profiles", self.state())

    def test_duplicate_credential_fields_are_never_overwritten(self):
        for label in ("certificate", "private key", "proteus identity"):
            with self.subTest(label=label):
                document = {"id": "existing", "title": "Workload", "vault": {"id": "work"},
                            "category": "SECURE_NOTE", "fields": [
                                {"id": "first", "label": label, "value": ""},
                                {"id": "second", "label": label, "value": ""}]}
                self.change(vaults={"work": [document], "protected": []})
                before = self.state()
                offset = len(self.requests())
                result = self.setup(success=False)
                self.assertIn("Duplicate credential fields", result.stderr)
                self.assertEqual(self.state(), before)
                self.assertFalse(any(tool == "op" and args[1] in ("create", "edit")
                                     for tool, args in self.requests()[offset:]))
                self.assert_no_cloud_mutations()

    def test_failed_ca_storage_never_creates_cloud_resources(self):
        self.change(op_failure="create")
        self.setup(success=False)
        self.assert_no_cloud_mutations()

    def test_missing_ca_key_is_never_silently_rotated(self):
        self.setup()
        state = self.state()
        state["vaults"]["protected"][0]["fields"] = [f for f in state["vaults"]["protected"][0]["fields"] if f["label"] != "private key"]
        self.change(**state)
        offset = len(self.requests())
        result = self.setup(REFERENCES, success=False)
        self.assertIn("CA item is incomplete", result.stderr)
        self.assertFalse(any(tool == "op" and args[1] in ("create", "edit") for tool, args in self.requests()[offset:]))

    def test_existing_resource_conflicts_are_not_overwritten(self):
        self.setup()
        state = self.state()
        state["Roles"][0]["AssumeRolePolicyDocument"]["Statement"][0]["Principal"] = {"AWS": "*"}
        self.change(**state)
        offset = len(self.requests())
        result = self.setup(REFERENCES, success=False)
        self.assertIn("role trust differs", result.stderr)
        self.assertFalse(any(arg.startswith(("update-", "attach-", "create-")) for _, args in self.requests()[offset:] for arg in args))

    def test_helper_sts_or_wrong_identity_fail_without_ready_output(self):
        for changes in ({"helper_failure": True}, {"aws_failure": "get-caller-identity"},
                        {"workload_account": "999999999999"},
                        {"workload_arn": "arn:aws:sts::123456789012:assumed-role/production/session"}):
            with self.subTest(changes=changes):
                self.change(helper_failure=False, aws_failure=None, workload_account=ACCOUNT,
                            workload_arn="arn:aws:sts::123456789012:assumed-role/proteus/session")
                self.change(**changes)
                self.setup(success=False)

    def test_missing_ca_item_does_not_generate_a_replacement(self):
        self.setup()
        state = self.state()
        state["vaults"]["protected"] = []
        self.change(**state)
        offset = len(self.requests())
        result = self.setup(REFERENCES, success=False)
        self.assertIn("restore its backup", result.stderr)
        self.assertFalse(any(tool == "op" and args[1] in ("create", "edit")
                             for tool, args in self.requests()[offset:]))

    def test_invalid_or_mismatched_stored_pair_is_preserved(self):
        self.setup()
        original = self.state()
        for replacement in ("invalid certificate", self.pair("protected")["certificate"]):
            with self.subTest(replacement=replacement[:20]):
                state = json.loads(json.dumps(original))
                for field in state["vaults"]["work"][0]["fields"]:
                    if field["label"] == "certificate":
                        field["value"] = replacement
                self.change(**state)
                offset = len(self.requests())
                self.setup(REFERENCES, success=False)
                self.assertEqual(self.state(), state)
                self.assertFalse(any(tool == "aws_signing_helper" for tool, _ in self.requests()[offset:]))

    def test_conflicting_anchor_and_profile_are_preserved(self):
        self.setup()
        original = self.state()
        for resource in ("trustAnchors", "profiles"):
            with self.subTest(resource=resource):
                state = json.loads(json.dumps(original))
                state[resource][0]["enabled"] = False
                self.change(**state)
                self.setup(REFERENCES, success=False)
                self.assertEqual(self.state(), state)

    def test_archived_or_ambiguous_ca_item_does_not_create_a_new_ca(self):
        self.setup()
        original = self.state()
        for mode in ("archived", "ambiguous"):
            with self.subTest(mode=mode):
                state = json.loads(json.dumps(original))
                if mode == "archived":
                    state["vaults"]["protected"][0]["state"] = "ARCHIVED"
                else:
                    duplicate = json.loads(json.dumps(state["vaults"]["protected"][0]))
                    duplicate["id"] = "another"
                    state["vaults"]["protected"].append(duplicate)
                self.change(**state)
                offset = len(self.requests())
                self.setup(REFERENCES, success=False)
                self.assertFalse(any(tool == "op" and args[1] in ("create", "edit")
                                     for tool, args in self.requests()[offset:]))

    def test_unrelated_item_category_is_never_modified(self):
        document = {"id": "login", "title": "Workload", "vault": {"id": "work"},
                    "category": "LOGIN", "fields": []}
        self.change(vaults={"work": [document]})
        before = self.state()
        result = self.setup(REFERENCES, success=False)
        self.assertIn("dedicated Secure Note", result.stderr)
        self.assertEqual(self.state(), before)
        self.assert_no_cloud_mutations()

    def test_same_item_rejected_before_secret_creation(self):
        result = self.setup("yes\nop://work/Workload/certificate\nop://work/Workload/certificate\n", success=False)
        self.assertIn("separate 1Password items", result.stderr)
        self.assert_no_cloud_mutations()

    def test_same_existing_item_selected_by_title_and_id_is_rejected(self):
        document = {"id": "existing", "title": "Workload", "vault": {"id": "work"},
                    "category": "SECURE_NOTE", "fields": []}
        self.change(vaults={"work": [document]})
        before = self.state()
        result = self.setup("yes\nop://work/Workload/certificate\nop://work/existing/certificate\n", success=False)
        self.assertIn("separate 1Password items", result.stderr)
        self.assertEqual(self.state(), before)
        self.assert_no_cloud_mutations()

    def test_interrupted_input_and_vault_read_failure_do_not_mutate(self):
        self.setup("yes\n", success=False)
        self.change(op_failure="list")
        self.setup(REFERENCES, success=False)
        self.assert_no_cloud_mutations()


if __name__ == "__main__":
    unittest.main()
