"""Exercise enrollment with separate host and guest homes and a real terminal."""

import json
import os
from pathlib import Path
import pty
import select
import shutil
import subprocess
import tempfile
import time
import unittest

from ssh_keys import generate_signing_key


ROOT = Path(__file__).resolve().parents[1]


class EnrollmentHarness(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.guest = self.directory / "guest"
        self.bin = self.directory / "bin"
        self.bin.mkdir()
        self.log = self.directory / "calls.jsonl"
        self.environment = {
            **os.environ,
            "HOME": str(self.directory / "host"),
            "XDG_CONFIG_HOME": str(self.directory / "config"),
            "PATH": f"{self.bin}:/usr/bin:/bin",
            "TEST_GUEST": str(self.guest),
            "TEST_LOG": str(self.log),
        }
        self.write_command(self.bin / "limactl", """
import json, os, subprocess, sys
args = sys.argv[1:]
with open(os.environ['TEST_LOG'], 'a') as log:
    log.write(json.dumps(args) + '\\n')
if args[0] == 'list':
    print(os.environ.get('TEST_VM_STATUS', 'Running'))
    sys.exit(0)
if args[0] != 'shell':
    sys.exit(90)  # Enrollment must never manage VM lifecycle.
while args[1].startswith('--'):
    args.pop(1)
environment = {**os.environ, 'HOME': os.environ['TEST_GUEST']}
sys.exit(subprocess.call(args[2:], env=environment))
""")
        self.write_command(self.guest / ".local/bin/mise", """
import os, sys
assert sys.argv[1:3] == ['exec', '--']
os.execv(sys.argv[3], sys.argv[3:])
""")
        self.write_command(self.guest / ".local/bin/claude", """
import os, pathlib, sys
credential = pathlib.Path.home() / '.claude/login'
if sys.argv[1:] == ['auth', 'login']:
    assert os.isatty(0) and os.isatty(1)
    if os.environ.get('TEST_LOGIN_FAIL'):
        sys.exit(1)
    print('Paste code:', flush=True)
    assert input() == 'test-authorization-code'
    credential.parent.mkdir(parents=True, exist_ok=True)
    credential.write_text('guest-session')
elif sys.argv[1:] == ['auth', 'status']:
    sys.exit(1 if os.environ.get('TEST_STATUS_FAIL') or not credential.exists() else 0)
else:
    sys.exit(91)
""")

    def write_command(self, path, body):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"#!{os.sys.executable}\n{body}")
        path.chmod(0o755)

    def run_enroll(self, *arguments, terminal=True, **environment):
        command = [str(ROOT / "enroll"), *arguments]
        env = {**self.environment, **environment}
        if not terminal:
            result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=10)
            return result.returncode, result.stdout + result.stderr
        master, slave = pty.openpty()
        try:
            with subprocess.Popen(command, env=env, stdin=slave, stdout=slave, stderr=slave) as process:
                os.close(slave)
                slave = None
                output = b""
                code_sent = False
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    if select.select([master], [], [], 0.1)[0]:
                        try:
                            chunk = os.read(master, 65536)
                        except OSError:
                            break
                        if not chunk:
                            break
                        output += chunk
                        if b"Paste code:" in output and not code_sent:
                            os.write(master, b"test-authorization-code\n")
                            code_sent = True
                    elif process.poll() is not None:
                        break
                if process.poll() is None:
                    process.kill()
                return process.wait(), output.decode()
        finally:
            os.close(master)
            if slave is not None:
                os.close(slave)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []


class EnrollmentTest(EnrollmentHarness):
    def test_claude_login_uses_guest_and_interactive_terminal(self):
        for instance in ("proteus", "custom-instance"):
            with self.subTest(instance=instance):
                arguments = ["claude"] if instance == "proteus" else ["claude", instance]
                status, output = self.run_enroll(*arguments)
                self.assertEqual(status, 0, output)
                self.assertIn(f"Enrolled Claude Code in Lima instance '{instance}'", output)
                self.assertTrue((self.guest / ".claude/login").exists())
                calls = self.calls()[-4:]
                self.assertEqual(len(calls), 4)
                self.assertEqual(calls[0][-1], instance)
                for call in calls[1:]:
                    self.assertIn("--start=false", call)
                    self.assertIn(instance, call)
                self.assertIn("--tty=true", calls[2])
                self.assertIn("auth status", calls[3][-1])
                self.assertFalse((Path(self.environment["HOME"]) / ".claude").exists())

    def test_claude_rejects_noninteractive_use(self):
        status, output = self.run_enroll("claude", terminal=False)
        self.assertEqual(status, 1)
        self.assertIn("requires an interactive terminal", output)
        self.assertEqual(self.calls(), [])

    def test_claude_requires_both_terminal_input_and_output(self):
        master, slave = pty.openpty()
        try:
            for stdin, stdout in ((slave, subprocess.PIPE), (subprocess.DEVNULL, slave)):
                with self.subTest(stdin=stdin, stdout=stdout):
                    result = subprocess.run(
                        [str(ROOT / "enroll"), "claude"],
                        env=self.environment, stdin=stdin, stdout=stdout,
                        stderr=subprocess.PIPE, text=True, timeout=10,
                    )
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("requires an interactive terminal", result.stderr)
                    self.assertEqual(self.calls(), [])
        finally:
            os.close(master)
            os.close(slave)

    def test_claude_rejects_missing_or_stopped_vm(self):
        for vm_status in ("", "Stopped"):
            with self.subTest(vm_status=vm_status):
                status, output = self.run_enroll("claude", TEST_VM_STATUS=vm_status)
                self.assertEqual(status, 1, output)
                self.assertNotIn("Enrolled", output)
                self.assertTrue(all(call[0] == "list" for call in self.calls()))

    def test_claude_rejects_unprovisioned_guest(self):
        for command in ("claude", "mise"):
            with self.subTest(command=command):
                path = self.guest / ".local/bin" / command
                missing = path.with_suffix(".missing")
                path.rename(missing)
                try:
                    if self.log.exists():
                        self.log.unlink()
                    status, output = self.run_enroll("claude")
                    self.assertEqual(status, 1)
                    self.assertIn("Run ./provision first", output)
                    self.assertEqual(len(self.calls()), 2)
                finally:
                    missing.rename(path)

    def test_claude_does_not_report_success_after_login_or_status_failure(self):
        for failure in ("TEST_LOGIN_FAIL", "TEST_STATUS_FAIL"):
            with self.subTest(failure=failure):
                status, output = self.run_enroll("claude", **{failure: "1"})
                self.assertEqual(status, 1, output)
                self.assertNotIn("Enrolled", output)

    def test_invalid_arguments(self):
        for arguments in ([], ["unknown"], ["claude", ""], ["claude", "-bad"], ["claude", "vm", "extra"]):
            with self.subTest(arguments=arguments):
                status, output = self.run_enroll(*arguments, terminal=False)
                self.assertEqual(status, 2)
                self.assertIn("Usage:", output)
                self.assertEqual(self.calls(), [])


class GitHubEnrollmentTest(EnrollmentHarness):
    def setUp(self):
        super().setUp()
        self.configuration = Path(self.environment["XDG_CONFIG_HOME"]) / "proteus/config"
        self.configuration.parent.mkdir(parents=True)
        self.configuration.write_text(
            "github_token_1password_reference=op://test/GitHub/token\n"
            "git_signing_key_1password_reference=op://test/Signing/private key\n"
        )
        self.fixture_key = generate_signing_key(self.directory)
        self.environment["TEST_SIGNING_KEY"] = str(self.fixture_key)
        self.op_log = self.directory / "op-calls.jsonl"
        self.environment["TEST_OP_LOG"] = str(self.op_log)
        self.write_command(self.bin / "op", """
import json, os, pathlib, sys
with open(os.environ['TEST_OP_LOG'], 'a') as log:
    log.write(json.dumps(sys.argv[1:]) + '\\n')
if sys.argv[1:] == ['read', 'op://test/GitHub/token']:
    if os.environ.get('TEST_OP_FAIL') == 'token':
        sys.exit(1)
    print('test-github-token')
elif sys.argv[1:] == ['read', 'op://test/Signing/private key?ssh-format=openssh']:
    print(pathlib.Path(os.environ['TEST_SIGNING_KEY']).read_text(), end='')
    if os.environ.get('TEST_OP_FAIL') == 'signing':
        sys.exit(1)
else:
    sys.exit(91)
""")
        self.write_command(self.bin / "gh", """
import os, sys
assert os.environ['GH_TOKEN'] == 'test-github-token'
assert sys.argv[1:] == ['auth', 'status', '--hostname', 'github.com']
sys.exit(1 if os.environ.get('TEST_STATUS_FAIL') else 0)
""")
        for relative in (".local/bin/proteus-enroll-github", ".local/bin/proteus-git-credential-github", ".local/bin/gh", ".local/lib/proteus/credentials.sh"):
            destination = self.guest / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / "dotfiles/home" / relative, destination)

    def test_github_streams_both_credentials_without_disclosing_secrets(self):
        status, output = self.run_enroll("github", terminal=False)
        self.assertEqual(status, 0, output)
        token = self.guest / ".local/share/proteus/secrets/github-token"
        self.assertEqual(token.read_text(), "test-github-token")
        self.assertEqual(token.stat().st_mode & 0o777, 0o600)
        self.assertNotIn("test-github-token", output)
        self.assertNotIn("test-github-token", self.log.read_text())
        signing_key = token.parent / "git-signing-key"
        self.assertEqual(signing_key.read_bytes(), self.fixture_key.read_bytes())
        self.assertEqual(signing_key.stat().st_mode & 0o777, 0o600)
        for line in self.fixture_key.read_text().splitlines():
            self.assertNotIn(line, output + self.log.read_text())
        self.assertEqual([json.loads(line) for line in self.op_log.read_text().splitlines()], [
            ["read", "op://test/GitHub/token"],
            ["read", "op://test/Signing/private key?ssh-format=openssh"],
        ])
        self.assertFalse((Path(self.environment["HOME"]) / ".local/share/proteus/secrets").exists())
        self.assertEqual(list(token.parent.glob(".github-enrollment.*")), [])

    def test_github_preserves_previous_token_when_validation_fails(self):
        self.assertEqual(self.run_enroll("github", terminal=False)[0], 0)
        token = self.guest / ".local/share/proteus/secrets/github-token"
        token.write_text("previous-token")
        status, output = self.run_enroll("github", terminal=False, TEST_STATUS_FAIL="1")
        self.assertEqual(status, 1, output)
        self.assertEqual(token.read_text(), "previous-token")

    def test_github_requires_both_references_before_contacting_vm(self):
        for config in ("", "github_token_1password_reference=op://test/GitHub/token\n",
                       "git_signing_key_1password_reference=op://test/Signing/private key\n"):
            with self.subTest(config=config):
                self.configuration.write_text(config)
                status, output = self.run_enroll("github", terminal=False)
                self.assertEqual(status, 1, output)
                self.assertIn("Run ./configure first", output)
                self.assertEqual(self.calls(), [])
                self.assertFalse(self.op_log.exists())

    def test_failed_secret_read_does_not_install_even_partially_read_credentials(self):
        for failure in ("token", "signing"):
            with self.subTest(failure=failure):
                status, output = self.run_enroll("github", terminal=False, TEST_OP_FAIL=failure)
                self.assertEqual(status, 1, output)
                self.assertIn("Could not read", output)
                self.assertNotIn("test-github-token", output)
                self.assertNotIn(self.fixture_key.read_text().strip(), output)
                self.assertFalse((self.guest / ".local/share/proteus/secrets").exists())

    def test_github_targets_custom_running_instance(self):
        status, output = self.run_enroll("github", "custom-instance", terminal=False)
        self.assertEqual(status, 0, output)
        self.assertTrue(all("custom-instance" in call for call in self.calls()))

    def test_github_checks_vm_before_reading_secrets(self):
        for vm_status in ("", "Stopped"):
            with self.subTest(vm_status=vm_status):
                status, output = self.run_enroll("github", terminal=False, TEST_VM_STATUS=vm_status)
                self.assertEqual(status, 1, output)
                self.assertTrue(all(call[0] == "list" for call in self.calls()))
                self.assertFalse(self.op_log.exists())

    def test_github_accepts_signing_reference_with_openssh_format_suffix(self):
        self.configuration.write_text(self.configuration.read_text().replace(
            "op://test/Signing/private key", "op://test/Signing/private key?ssh-format=openssh",
        ))
        status, output = self.run_enroll("github", terminal=False)
        self.assertEqual(status, 0, output)


if __name__ == "__main__":
    unittest.main()
