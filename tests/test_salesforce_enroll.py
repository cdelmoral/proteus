"""Exercise Salesforce enrollment with real Managed Dotfiles and a simulated CLI."""

import json
import os
from pathlib import Path
import pty
import shutil
import subprocess
import unittest

from test_enroll import EnrollmentHarness, ROOT


GUEST_FILES = (
    ".local/bin/sf",
    ".local/bin/proteus-enroll-salesforce",
    ".local/bin/proteus-capture-browser-url",
)
# Provisioning links the npm-installed CLI and managed Node beneath the sf launcher.
CLI = ".local/share/proteus/salesforce-cli/sf"
NODE = ".local/share/proteus/salesforce-cli/node"
TOKEN = "sensitive-access-token"
DEFAULT_URL = "https://login.salesforce.com"
MY_DOMAIN = "https://example.my.salesforce.com"
REFERENCE = "op://test/GitHub/token"


class SalesforceEnrollmentTest(EnrollmentHarness):
    def setUp(self):
        super().setUp()
        for relative in GUEST_FILES:
            shutil.copy2(ROOT / "dotfiles/home" / relative, self.guest / relative)
        self.cli_log = self.directory / "sf-calls.jsonl"
        self.environment["TEST_SF_LOG"] = str(self.cli_log)
        self.write_command(self.guest / NODE, """
import os, sys
os.execv(sys.argv[1], sys.argv[1:])
""")
        # Only managed Node and the npm-installed CLI are simulated. Like the open package,
        # login runs BROWSER detached with output discarded.
        self.write_command(self.guest / CLI, f"""
import json, os, pathlib, subprocess, sys
args = sys.argv[1:]
names = ('SF_USE_GENERIC_UNIX_KEYCHAIN', 'SF_DISABLE_TELEMETRY', 'SF_CONTAINER_MODE', 'SFDX_CONTAINER_MODE')
with open(os.environ['TEST_SF_LOG'], 'a') as log:
    log.write(json.dumps({{'args': args, 'env': {{name: os.environ.get(name) for name in names}}}}) + '\\n')
authorization = pathlib.Path.home() / '.sfdx/devhub.json'
if args[:3] == ['org', 'login', 'web']:
    instance = args[args.index('--instance-url') + 1]
    url = instance + '/services/oauth2/authorize?client_id=PlatformCLI&state=test-state'
    browser = '/bin/false' if os.environ.get('TEST_BROWSER_FAIL') else os.environ.get('BROWSER', '/bin/false')
    opened = subprocess.Popen([browser, url], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, start_new_session=True).wait()
    if opened:
        print('Error (BrowserOpenError): Unable to open the browser.', file=sys.stderr)
        sys.exit(1)
    if os.environ.get('TEST_LOGIN_FAIL'):
        print('Error (AuthCodeExchangeError): Invalid authorization.', file=sys.stderr)
        sys.exit(1)
    authorization.parent.mkdir(parents=True, exist_ok=True)
    authorization.write_text(json.dumps({{'instance': instance}}))
    print('Successfully authorized devhub-user@example.com')
elif args == ['org', 'display', '--target-org', 'devhub', '--json']:
    connected = authorization.exists() and not os.environ.get('TEST_DISCONNECTED')
    print(json.dumps({{'status': 0, 'result': {{
        'alias': 'devhub', 'accessToken': '{TOKEN}',
        'connectedStatus': 'Connected' if connected else 'RefreshTokenAuthError',
    }}}}))
else:
    sys.exit(92)
""")

    @property
    def configuration(self):
        return Path(self.environment["XDG_CONFIG_HOME"]) / "proteus/config"

    def configure(self, reference, login_url):
        result = subprocess.run(
            [str(ROOT / "configure")],
            input=f"{reference}\nop://test/Signing/private key\n{login_url}\n",
            env=self.environment, capture_output=True, text=True, timeout=10,
        )
        return result.returncode, result.stdout + result.stderr

    def login_url(self):
        login = self.logins()[-1]["args"]
        return login[login.index("--instance-url") + 1]

    def cli_calls(self):
        return [json.loads(line) for line in self.cli_log.read_text().splitlines()] if self.cli_log.exists() else []

    def logins(self):
        return [call for call in self.cli_calls() if call["args"][:3] == ["org", "login", "web"]]

    def test_enrollment_prints_url_and_saves_default_dev_hub(self):
        status, output = self.run_enroll("salesforce", SF_CONTAINER_MODE="true", SFDX_CONTAINER_MODE="true")
        self.assertEqual(status, 0, output)
        self.assertIn("https://login.salesforce.com/services/oauth2/authorize?client_id=PlatformCLI&state=test-state", output)
        self.assertIn("macOS browser", output)
        self.assertIn("Enrolled the Dev Hub User in Lima instance 'proteus'", output)
        self.assertNotIn(TOKEN, output)
        [login] = self.logins()
        self.assertEqual(login["args"][3:], [
            "--instance-url", "https://login.salesforce.com", "--alias", "devhub", "--set-default-dev-hub",
        ])
        self.assertEqual(login["env"], {
            "SF_USE_GENERIC_UNIX_KEYCHAIN": "true", "SF_DISABLE_TELEMETRY": "true",
            "SF_CONTAINER_MODE": None, "SFDX_CONTAINER_MODE": None,
        })
        self.assertEqual(self.cli_calls()[-1]["args"], ["org", "display", "--target-org", "devhub", "--json"])

    def test_salesforce_custom_instance_never_manages_vm_lifecycle(self):
        status, output = self.run_enroll("salesforce", "custom-instance")
        self.assertEqual(status, 0, output)
        self.assertIn("Enrolled the Dev Hub User in Lima instance 'custom-instance'", output)
        for call in self.calls():
            self.assertIn(call[0], ("list", "shell"))
            self.assertEqual(call[-1] if call[0] == "list" else call[call.index("--start=false") + 1], "custom-instance")

    def test_salesforce_repeat_enrollment_performs_new_login(self):
        for _ in range(2):
            status, output = self.run_enroll("salesforce")
            self.assertEqual(status, 0, output)
        self.assertEqual(len(self.logins()), 2)

    def test_salesforce_requires_terminal_input_and_output(self):
        status, output = self.run_enroll("salesforce", terminal=False)
        self.assertEqual(status, 1)
        self.assertIn("requires an interactive terminal", output)
        master, slave = pty.openpty()
        try:
            for stdin, stdout in ((slave, subprocess.PIPE), (subprocess.DEVNULL, slave)):
                with self.subTest(stdin=stdin, stdout=stdout):
                    result = subprocess.run(
                        [str(ROOT / "enroll"), "salesforce"],
                        env=self.environment, stdin=stdin, stdout=stdout,
                        stderr=subprocess.PIPE, text=True, timeout=10,
                    )
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("requires an interactive terminal", result.stderr)
        finally:
            os.close(master)
            os.close(slave)
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.cli_calls(), [])

    def test_salesforce_rejects_missing_or_stopped_vm(self):
        for vm_status in ("", "Stopped"):
            with self.subTest(vm_status=vm_status):
                status, output = self.run_enroll("salesforce", TEST_VM_STATUS=vm_status)
                self.assertEqual(status, 1, output)
                self.assertNotIn("Enrolled", output)
                self.assertTrue(all(call[0] == "list" for call in self.calls()))
        self.assertEqual(self.cli_calls(), [])

    def test_salesforce_rejects_unprovisioned_guest(self):
        for relative in (*GUEST_FILES, CLI, NODE):
            with self.subTest(relative=relative):
                path = self.guest / relative
                missing = path.with_name(path.name + ".missing")
                path.rename(missing)
                try:
                    status, output = self.run_enroll("salesforce")
                    self.assertEqual(status, 1, output)
                    self.assertIn("Run ./provision first", output)
                    self.assertEqual(self.cli_calls(), [])
                finally:
                    missing.rename(path)

    def test_salesforce_failures_never_report_success(self):
        for failure in ("TEST_LOGIN_FAIL", "TEST_BROWSER_FAIL", "TEST_DISCONNECTED"):
            with self.subTest(failure=failure):
                status, output = self.run_enroll("salesforce", **{failure: "1"})
                self.assertEqual(status, 1, output)
                self.assertNotIn("Enrolled", output)
                self.assertIn("Salesforce Credential Enrollment failed", output)
                self.assertNotIn(TOKEN, output)

    def test_configured_my_domain_reaches_login(self):
        status, output = self.configure(REFERENCE, MY_DOMAIN)
        self.assertEqual(status, 0, output)
        status, output = self.run_enroll("salesforce")
        self.assertEqual(status, 0, output)
        self.assertEqual(self.login_url(), MY_DOMAIN)
        self.assertIn(MY_DOMAIN + "/services/oauth2/authorize", output)

    def test_pasted_trailing_slash_is_saved_without_path(self):
        status, output = self.configure(REFERENCE, MY_DOMAIN + "/")
        self.assertEqual(status, 0, output)
        self.assertIn(f"salesforce_login_url={MY_DOMAIN}\n", self.configuration.read_text())

    def test_configuration_without_login_url_uses_standard_login(self):
        self.configuration.parent.mkdir(parents=True)
        self.configuration.write_text(f"github_token_1password_reference={REFERENCE}\n")
        status, output = self.run_enroll("salesforce")
        self.assertEqual(status, 0, output)
        self.assertEqual(self.login_url(), DEFAULT_URL)

    def test_blank_answers_keep_current_values_or_defaults(self):
        status, output = self.configure(REFERENCE, "")
        self.assertEqual(status, 0, output)
        self.assertIn(f"[{DEFAULT_URL}]", output)
        self.assertEqual(self.configure(REFERENCE, MY_DOMAIN)[0], 0)
        saved = self.configuration.read_text()
        status, output = self.configure("", "")
        self.assertEqual(status, 0, output)
        self.assertIn(f"[{REFERENCE}]", output)
        self.assertIn(f"[{MY_DOMAIN}]", output)
        self.assertEqual(self.configuration.read_text(), saved)

    def test_saving_either_value_preserves_the_other(self):
        self.assertEqual(self.configure(REFERENCE, MY_DOMAIN)[0], 0)
        self.assertEqual(self.configure("op://test/GitHub/rotated", "")[0], 0)
        self.assertEqual(self.configure("", "https://other.my.salesforce.com")[0], 0)
        self.assertEqual(sorted(self.configuration.read_text().splitlines()), [
            "git_signing_key_1password_reference=op://test/Signing/private key",
            "github_token_1password_reference=op://test/GitHub/rotated",
            "proteus_aws_enabled=false",
            "salesforce_login_url=https://other.my.salesforce.com",
        ])

    def test_github_reference_is_still_required(self):
        status, output = self.configure("", MY_DOMAIN)
        self.assertEqual(status, 1, output)
        self.assertIn("reference is required", output)
        self.assertFalse(self.configuration.exists())

    def test_invalid_login_urls_leave_configuration_unchanged(self):
        self.assertEqual(self.configure(REFERENCE, MY_DOMAIN)[0], 0)
        saved = self.configuration.read_bytes()
        for url in (
            "http://login.salesforce.com", "login.salesforce.com",
            "https://login.salesforce.com/path", "https://login.salesforce.com?next=x",
            "https://login.salesforce.com#fragment", "https://salesforce.com",
            "https://example.com", "https://login.salesforce.com.example.com",
            "https://examplesalesforce.com", "https://user@login.salesforce.com",
            "https://login.salesforce.com:8443",
        ):
            with self.subTest(url=url):
                status, output = self.configure("op://test/GitHub/rotated", url)
                self.assertEqual(status, 1, output)
                self.assertIn("Salesforce login URL", output)
                self.assertEqual(self.configuration.read_bytes(), saved)


if __name__ == "__main__":
    unittest.main()
