"""Exercise TWG enrollment with the real helper and a simulated vendor CLI."""

import json
from pathlib import Path
import shutil

from test_enroll import EnrollmentHarness, ROOT


class TeamworkGraphEnrollmentTest(EnrollmentHarness):
    def setUp(self):
        super().setUp()
        helper = ".local/bin/proteus-enroll-twg"
        shutil.copy2(ROOT / "dotfiles/home" / helper, self.guest / helper)
        self.cli_log = self.directory / "twg-calls.jsonl"
        self.environment["TEST_TWG_LOG"] = str(self.cli_log)
        # Do not inherit the real user's session bus in this simulated guest.
        self.environment.pop("XDG_RUNTIME_DIR", None)
        self.environment.pop("DBUS_SESSION_BUS_ADDRESS", None)
        self.write_command(self.guest / ".local/bin/twg", """
import json, os, pathlib, sys
args = sys.argv[1:]
with open(os.environ['TEST_TWG_LOG'], 'a') as log:
    log.write(json.dumps(args) + '\\n')
credential = pathlib.Path.home() / '.config/twg/auth-profiles.json'
if args == ['doctor', '--basic']:
    if not credential.exists() or os.environ.get('TEST_DOCTOR_FAIL'):
        print('Not authenticated', file=sys.stderr)
        sys.exit(1)
elif args == ['login', '--force']:
    assert os.isatty(0) and os.isatty(1)
    print('Open https://auth.example.test/verify and confirm code ABCD')
    if os.environ.get('TEST_LOGIN_FAIL'):
        sys.exit(1)
    credential.parent.mkdir(parents=True, exist_ok=True)
    credential.write_text('guest-oauth-session')
elif args == ['upkeep', 'enable']:
    assert os.environ['XDG_RUNTIME_DIR'] == f'/run/user/{os.getuid()}'
    assert os.environ['DBUS_SESSION_BUS_ADDRESS'] == f'unix:path=/run/user/{os.getuid()}/bus'
    sys.exit(1 if os.environ.get('TEST_UPKEEP_FAIL') else 0)
else:
    sys.exit(91)  # No product probes, write tests, or service-health queries.
""")
        self.write_command(self.bin / "sudo", """
import json, os, pwd, sys
args = sys.argv[1:]
with open(os.environ['TEST_TWG_LOG'], 'a') as log:
    log.write(json.dumps(['sudo', *args]) + '\\n')
assert args == ['-n', 'loginctl', 'enable-linger', pwd.getpwuid(os.getuid()).pw_name]
sys.exit(1 if os.environ.get('TEST_LINGER_FAIL') else 0)
""")

    def cli_calls(self):
        return [json.loads(line) for line in self.cli_log.read_text().splitlines()] if self.cli_log.exists() else []

    def test_fresh_enrollment_authorizes_guest_and_enables_upkeep(self):
        status, output = self.run_enroll("twg", "custom-instance")
        self.assertEqual(status, 0, output)
        self.assertIn("macOS browser", output)
        self.assertIn("https://auth.example.test/verify", output)
        self.assertIn("Enrolled Teamwork Graph in Lima instance 'custom-instance'", output)
        self.assertNotIn("guest-oauth-session", output)
        self.assertTrue((self.guest / ".config/twg/auth-profiles.json").exists())
        self.assertFalse((Path(self.environment["HOME"]) / ".config/twg").exists())
        self.assertIn(["login", "--force"], self.cli_calls())
        self.assertEqual(self.cli_calls()[-1], ["upkeep", "enable"])
        for call in self.calls():
            self.assertIn(call[0], ("list", "shell"))
            self.assertIn("custom-instance", call)
            if call[0] == "shell":
                self.assertIn("--start=false", call)

    def test_repeat_enrollment_preserves_healthy_authorization(self):
        self.assertEqual(self.run_enroll("twg")[0], 0)
        credential = self.guest / ".config/twg/auth-profiles.json"
        credential.write_text("existing-oauth-session")
        self.cli_log.unlink()
        status, output = self.run_enroll("twg")
        self.assertEqual(status, 0, output)
        self.assertEqual(credential.read_text(), "existing-oauth-session")
        self.assertNotIn(["login", "--force"], self.cli_calls())
        self.assertEqual(self.cli_calls().count(["doctor", "--basic"]), 1)

    def test_failures_never_report_success_and_retry_preserves_login(self):
        for failure in ("TEST_LOGIN_FAIL", "TEST_DOCTOR_FAIL", "TEST_LINGER_FAIL", "TEST_UPKEEP_FAIL"):
            with self.subTest(failure=failure):
                credential = self.guest / ".config/twg/auth-profiles.json"
                credential.unlink(missing_ok=True)
                status, output = self.run_enroll("twg", **{failure: "1"})
                self.assertEqual(status, 1, output)
                self.assertNotIn("Enrolled Teamwork Graph", output)
                self.assertIn("Completed steps were preserved", output)
                if failure == "TEST_UPKEEP_FAIL":
                    self.assertTrue(credential.exists())
                    self.cli_log.unlink()
                    self.assertEqual(self.run_enroll("twg")[0], 0)
                    self.assertNotIn(["login", "--force"], self.cli_calls())

    def test_missing_terminal_or_vm_never_starts_login(self):
        status, output = self.run_enroll("twg", terminal=False)
        self.assertEqual(status, 1, output)
        self.assertIn("interactive terminal", output)
        self.assertEqual(self.calls(), [])
        for vm_status in ("", "Stopped"):
            with self.subTest(vm_status=vm_status):
                status, output = self.run_enroll("twg", TEST_VM_STATUS=vm_status)
                self.assertEqual(status, 1, output)
                self.assertTrue(all(call[0] == "list" for call in self.calls()))
        self.assertEqual(self.cli_calls(), [])

    def test_missing_cli_or_helper_requires_provisioning(self):
        for name in ("twg", "proteus-enroll-twg"):
            with self.subTest(name=name):
                path = self.guest / ".local/bin" / name
                missing = path.with_suffix(".missing")
                path.rename(missing)
                try:
                    status, output = self.run_enroll("twg")
                    self.assertEqual(status, 1, output)
                    self.assertIn("Run ./provision first", output)
                    self.assertEqual(self.cli_calls(), [])
                finally:
                    missing.rename(path)
