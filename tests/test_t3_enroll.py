"""Exercise real enrollment orchestration with simulated T3 and systemd tools."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import pty
import shutil
import subprocess

from test_enroll import EnrollmentHarness, ROOT


HELPER = ROOT / "dotfiles/home/.local/bin/proteus-enroll-t3"


class T3EnrollmentTest(EnrollmentHarness):
    def setUp(self):
        super().setUp()
        self.environment["T3CODE_HOME"] = str(self.guest / ".t3")
        self.environment["TEST_SERVER_PID"] = str(os.getpid())
        self.state = self.guest / ".t3/test-state.json"
        self.tool_log = self.directory / "t3-calls.jsonl"
        self.environment["TEST_TOOL_LOG"] = str(self.tool_log)
        helper = self.guest / ".local/bin/proteus-enroll-t3"
        shutil.copy2(HELPER, helper)
        common = """
import datetime, json, os, pathlib, sys
home = pathlib.Path.home()
state_file = home / '.t3/test-state.json'
state = json.loads(state_file.read_text()) if state_file.exists() else {}
args = sys.argv[1:]
with open(os.environ['TEST_TOOL_LOG'], 'a') as log:
    log.write(json.dumps([pathlib.Path(sys.argv[0]).name, *args]) + '\\n')
def save():
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state))
"""
        self.write_command(self.bin / "systemctl", common + """
if args == ['--user', 'show-environment']:
    sys.exit(1 if os.environ.get('TEST_MANAGER_FAIL') else 0)
assert args == ['--user', 'show', 't3code.service', '--property=LoadState,ActiveState,UnitFileState,Environment']
if not state.get('installed'):
    print('LoadState=not-found')
    sys.exit(1)
print('LoadState=loaded')
print('ActiveState=' + ('active' if state.get('active') else 'inactive'))
print('UnitFileState=' + ('enabled' if state.get('enabled') else 'disabled'))
print('Environment=T3CODE_HOME=' + str(home / ('.other-t3' if os.environ.get('TEST_OTHER_BASE') else '.t3')))
""")
        self.write_command(self.bin / "loginctl", common + """
assert args == ['show-user', str(os.getuid()), '--property=Linger', '--value']
if os.environ.get('TEST_LINGER_STATUS_FAIL'):
    sys.exit(1)
print('yes' if state.get('linger') else 'no')
""")
        self.write_command(self.bin / "sudo", common + """
assert args == ['-n', 'loginctl', 'enable-linger', str(os.getuid())]
if os.environ.get('TEST_SUDO_FAIL'):
    sys.exit(1)
state['linger'] = not bool(os.environ.get('TEST_LINGER_UNCHANGED'))
save()
""")
        self.write_command(self.guest / ".local/bin/t3", common + """
if os.environ.get('TEST_EXPECTED_PATH'):
    assert os.environ['PATH'] == os.environ['TEST_EXPECTED_PATH']
assert args[-2:] == ['--base-dir', str(home / '.t3')]
args = args[:-2]
if args == ['connect', 'status', '--json']:
    if os.environ.get('TEST_T3_STATUS_FAIL'):
        print('sensitive-status-detail', file=sys.stderr)
        sys.exit(1)
    if os.environ.get('TEST_T3_STATUS_INVALID'):
        print('sensitive-invalid-status')
        sys.exit(0)
    print(json.dumps({
        'desired': state.get('desired', False),
        'authenticated': state.get('authenticated', False),
        'linked': state.get('linked', False),
        'relayClient': {'status': 'missing' if os.environ.get('TEST_NPM_RELAY_MISSING') and pathlib.Path(sys.argv[0]) == home / '.local/bin/t3' else state.get('relay', 'missing')},
        'cloudUserId': 'sensitive-identity', 'relayUrl': 'sensitive-relay-address',
    }))
    sys.exit(0)
assert args in (['connect', '--headless'], ['connect', 'link', '--headless'])
assert os.isatty(0) and os.isatty(1)
if os.environ.get('TEST_RELAY_DECLINED'):
    sys.exit(0)
state['relay'] = 'available'
save()
if os.environ.get('TEST_T3_LOGIN_FAIL'):
    sys.exit(1)
state['authenticated'] = state['desired'] = True
state['linked'] = not bool(os.environ.get('TEST_LINK_INCOMPLETE'))
secrets = home / '.t3/userdata/secrets'
secrets.mkdir(parents=True, exist_ok=True)
(secrets / 'test-credential').write_text('guest-t3-session')
(secrets / 'cloud-cli-desired-link.bin').write_bytes(b'managed')
save()
if args == ['connect', 'link', '--headless'] or os.environ.get('TEST_SERVICE_FAILED'):
    sys.exit(0)
assert not state.get('installed'), 'Onboarding must not replace an existing service'
state.update(installed=True, active=True, enabled=not bool(os.environ.get('TEST_SERVICE_DISABLED')),
             linked=not bool(os.environ.get('TEST_LINK_DELAYED')))
save()
version = '0.0.45'
pinned = home / '.t3/runtime/versions' / version
pinned.mkdir(parents=True, exist_ok=True)
import shutil
shutil.copy2(sys.argv[0], pinned / 't3')
(pinned / '.install-complete').write_text(version)
(pinned.parent.parent / 'service-state.json').write_text(json.dumps({'protocol': 3, 'activeVersion': version}))
unit = home / '.config/systemd/user/t3code.service'
unit.parent.mkdir(parents=True, exist_ok=True)
unit.write_text('test-user-service')
runtime = home / '.t3/userdata/server-runtime.json'
if os.environ.get('TEST_NO_SERVER_RUNTIME'):
    sys.exit(0)
runtime.write_text(json.dumps({
    'version': 1, 'pid': int(os.environ['TEST_SERVER_PID']), 'serviceManaged': True,
    'startedAt': datetime.datetime.now(datetime.timezone.utc).isoformat(),
}))
""")

    def tools(self):
        return [json.loads(line) for line in self.tool_log.read_text().splitlines()] if self.tool_log.exists() else []

    def seed_enrollment(self, **overrides):
        state = dict(installed=True, active=True, enabled=True, linger=True,
                     desired=True, authenticated=True, linked=True, relay="available")
        state.update(overrides)
        self.state.parent.mkdir(parents=True, exist_ok=True)
        self.state.write_text(json.dumps(state))
        secrets = self.guest / ".t3/userdata/secrets"
        secrets.mkdir(parents=True, exist_ok=True)
        desired = secrets / "cloud-cli-desired-link.bin"
        desired.write_bytes(b"managed")
        runtime = secrets.parent / "server-runtime.json"
        runtime.write_text(json.dumps({
            "version": 1, "pid": os.getpid(), "serviceManaged": True,
            "startedAt": datetime.now(timezone.utc).isoformat(),
        }))
        version = overrides.get("service_version", "0.0.45")
        pinned = self.guest / ".t3/runtime/versions" / version
        pinned.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.guest / ".local/bin/t3", pinned / "t3")
        (pinned / ".install-complete").write_text(version)
        (pinned.parent.parent / "service-state.json").write_text(json.dumps({"protocol": 3, "activeVersion": version}))
        return desired, runtime

    def test_fresh_enrollment_and_repeat_preserve_guest_state(self):
        for instance in ("proteus", "custom-instance"):
            with self.subTest(instance=instance):
                arguments = ["t3"] if instance == "proteus" else ["t3", instance]
                status, output = self.run_enroll(*arguments)
                self.assertEqual(status, 0, output)
                self.assertIn(f"Enrolled T3 in Lima instance '{instance}'", output)
                self.assertIn("connect from another device", output)
                for call in self.calls()[-3:]:
                    if call[0] == "shell":
                        self.assertIn("--start=false", call)
                        self.assertIn(instance, call)
                state = json.loads(self.state.read_text())
                self.assertTrue(all(state[name] for name in ("authenticated", "linked", "installed", "active", "enabled", "linger")))
                self.assertFalse((Path(self.environment["HOME"]) / ".t3").exists())
                self.assertNotIn("guest-t3-session", output)
                self.assertNotIn("sensitive-", output)
        self.assertEqual(sum(call[0] == "sudo" for call in self.tools()), 1)
        self.assertEqual(sum(call[0] == "t3" and call[1] == "connect" and "--headless" in call for call in self.tools()), 1)

    def test_t3_requires_terminal_input_and_output(self):
        status, output = self.run_enroll("t3", terminal=False)
        self.assertEqual(status, 1)
        self.assertIn("requires an interactive terminal", output)
        self.assertEqual(self.calls(), [])
        master, slave = pty.openpty()
        try:
            for stdin, stdout in ((slave, subprocess.PIPE), (subprocess.DEVNULL, slave)):
                with self.subTest(stdin=stdin, stdout=stdout):
                    result = subprocess.run(
                        [str(ROOT / "enroll"), "t3"], env=self.environment,
                        stdin=stdin, stdout=stdout, stderr=subprocess.PIPE, text=True, timeout=10,
                    )
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("requires an interactive terminal", result.stderr)
                    self.assertEqual(self.calls(), [])
        finally:
            os.close(master)
            os.close(slave)

    def test_t3_rejects_missing_or_stopped_vm(self):
        for vm_status in ("", "Stopped"):
            with self.subTest(vm_status=vm_status):
                status, output = self.run_enroll("t3", TEST_VM_STATUS=vm_status)
                self.assertEqual(status, 1, output)
                self.assertNotIn("Enrolled T3", output)
                self.assertEqual(self.tools(), [])

    def test_enrollment_without_mise_preserves_project_path(self):
        (self.guest / ".local/bin/mise").unlink()
        (self.guest / ".node-version").write_text("99.99.99")
        self.environment["TEST_EXPECTED_PATH"] = self.environment["PATH"]
        status, output = self.run_enroll("t3")
        self.assertEqual(status, 0, output)

    def test_t3_rejects_unprovisioned_guest(self):
        for command in ("t3", "proteus-enroll-t3"):
            with self.subTest(command=command):
                path = self.guest / ".local/bin" / command
                missing = path.with_suffix(".missing")
                path.rename(missing)
                try:
                    status, output = self.run_enroll("t3")
                    self.assertEqual(status, 1)
                    self.assertIn("Run ./provision first", output)
                    self.assertEqual(self.tools(), [])
                finally:
                    missing.rename(path)

    def test_successful_cli_exit_does_not_hide_incomplete_setup(self):
        for failure in ("TEST_RELAY_DECLINED", "TEST_SERVICE_FAILED", "TEST_SERVICE_DISABLED"):
            with self.subTest(failure=failure):
                shutil.rmtree(self.guest / ".t3", ignore_errors=True)
                shutil.rmtree(self.guest / ".config", ignore_errors=True)
                status, output = self.run_enroll("t3", **{failure: "1"})
                self.assertEqual(status, 1, output)
                self.assertIn("incomplete", output)
                self.assertNotIn("Enrolled T3", output)
                if failure != "TEST_RELAY_DECLINED":
                    self.assertEqual((self.guest / ".t3/userdata/secrets/test-credential").read_text(), "guest-t3-session")

    def test_retry_reuses_saved_authorization_after_service_failure(self):
        status, output = self.run_enroll("t3", TEST_SERVICE_FAILED="1")
        self.assertEqual(status, 1, output)
        status, output = self.run_enroll("t3")
        self.assertEqual(status, 0, output)
        self.assertTrue(json.loads(self.state.read_text())["linked"])

    def test_prerequisite_or_login_failure_cannot_report_success(self):
        for failure in ("TEST_MANAGER_FAIL", "TEST_LINGER_STATUS_FAIL", "TEST_SUDO_FAIL", "TEST_LINGER_UNCHANGED", "TEST_T3_LOGIN_FAIL"):
            with self.subTest(failure=failure):
                shutil.rmtree(self.guest / ".t3", ignore_errors=True)
                status, output = self.run_enroll("t3", **{failure: "1"})
                self.assertEqual(status, 1, output)
                self.assertNotIn("Enrolled T3", output)

    def test_unreadable_status_is_sanitized(self):
        for failure in ("TEST_T3_STATUS_FAIL", "TEST_T3_STATUS_INVALID"):
            with self.subTest(failure=failure):
                status, output = self.run_enroll("t3", **{failure: "1"})
                self.assertEqual(status, 1, output)
                self.assertNotIn("sensitive-", output)
                self.assertNotIn("Enrolled T3", output)

    def test_healthy_service_is_untouched_despite_cli_version_difference(self):
        desired, runtime = self.seed_enrollment(service_version="0.0.44")
        before = (desired.read_bytes(), desired.stat().st_mtime_ns, runtime.read_bytes(), self.state.read_bytes())
        status, output = self.run_enroll("t3", TEST_NPM_RELAY_MISSING="1")
        self.assertEqual(status, 0, output)
        after = (desired.read_bytes(), desired.stat().st_mtime_ns, runtime.read_bytes(), self.state.read_bytes())
        self.assertEqual(before, after)
        self.assertFalse(any("--headless" in call or call[0] == "sudo" for call in self.tools()))

    def test_existing_service_repairs_are_explicit(self):
        for override in ({"active": False}, {"enabled": False}):
            with self.subTest(override=override):
                self.seed_enrollment(**override)
                status, output = self.run_enroll("t3")
                self.assertEqual(status, 1, output)
                self.assertIn("explicitly", output)
                self.assertNotIn("Enrolled T3", output)
                self.assertFalse(any("--headless" in call for call in self.tools()))

    def test_foreground_server_is_not_taken_over(self):
        _, runtime = self.seed_enrollment(installed=False)
        data = json.loads(runtime.read_text())
        data["serviceManaged"] = False
        runtime.write_text(json.dumps(data))
        status, output = self.run_enroll("t3")
        self.assertEqual(status, 1, output)
        self.assertIn("foreground T3 server", output)
        self.assertFalse(any("--headless" in call for call in self.tools()))

    def test_linking_running_service_preserves_work_and_completes_enrollment(self):
        _, runtime = self.seed_enrollment(desired=False, authenticated=False, linked=False)
        original_runtime = runtime.read_bytes()
        status, output = self.run_enroll("t3")
        self.assertEqual(status, 0, output)
        self.assertIn("Enrolled T3", output)
        self.assertEqual(original_runtime, runtime.read_bytes())
        state = json.loads(self.state.read_text())
        self.assertTrue(state["authenticated"] and state["desired"] and state["linked"])
        self.assertTrue(any(call[1:4] == ["connect", "link", "--headless"] for call in self.tools()))

    def test_link_saved_after_startup_does_not_require_restart(self):
        desired, _ = self.seed_enrollment()
        os.utime(desired, (desired.stat().st_atime, desired.stat().st_mtime + 10))
        status, output = self.run_enroll("t3")
        self.assertEqual(status, 0, output)
        self.assertIn("Enrolled T3", output)
        self.assertFalse(any("--headless" in call for call in self.tools()))

    def test_saved_link_mode_is_owned_by_t3(self):
        desired, runtime = self.seed_enrollment()
        desired.write_bytes(b"publish_only")
        original_runtime = runtime.read_bytes()
        status, output = self.run_enroll("t3")
        self.assertEqual(status, 0, output)
        self.assertEqual(desired.read_bytes(), b"publish_only")
        self.assertEqual(runtime.read_bytes(), original_runtime)
        self.assertFalse(any("--headless" in call for call in self.tools()))

    def test_other_data_directory_is_left_alone(self):
        self.seed_enrollment()
        status, output = self.run_enroll("t3", TEST_OTHER_BASE="1")
        self.assertEqual(status, 1, output)
        self.assertIn("another data directory", output)
        self.assertFalse(any("--headless" in call for call in self.tools()))

    def test_pending_runtime_update_does_not_block_enrollment(self):
        self.seed_enrollment()
        marker = self.guest / ".t3/runtime/.restart-pending"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
        status, output = self.run_enroll("t3")
        self.assertEqual(status, 0, output)
        self.assertTrue(marker.exists())
        self.assertFalse(any("--headless" in call for call in self.tools()))

    def test_unrecognized_runtime_state_cannot_trigger_onboarding(self):
        _, runtime = self.seed_enrollment(installed=False)
        runtime.write_text(json.dumps({"version": 1, "pid": "invalid", "serviceManaged": False}))
        status, output = self.run_enroll("t3")
        self.assertEqual(status, 1, output)
        self.assertIn("safely identify", output)
        self.assertNotIn("Traceback", output)
        self.assertFalse(any("--headless" in call for call in self.tools()))

    def test_missing_pinned_runtime_metadata_does_not_block_healthy_service(self):
        self.seed_enrollment()
        shutil.rmtree(self.guest / ".t3/runtime")
        status, output = self.run_enroll("t3")
        self.assertEqual(status, 0, output)
        self.assertFalse((self.guest / ".t3/runtime").exists())
        self.assertFalse(any("--headless" in call for call in self.tools()))

    def test_missing_private_link_and_server_files_do_not_block_healthy_service(self):
        desired, runtime = self.seed_enrollment()
        desired.unlink()
        runtime.unlink()
        status, output = self.run_enroll("t3")
        self.assertEqual(status, 0, output)
        self.assertFalse(any("--headless" in call for call in self.tools()))

    def test_fresh_enrollment_does_not_wait_for_server_runtime_file(self):
        status, output = self.run_enroll("t3", TEST_NO_SERVER_RUNTIME="1")
        self.assertEqual(status, 0, output)
        self.assertIn("Enrolled T3", output)
        self.assertNotIn("Verifying local T3 startup", output)

    def test_missing_environment_link_reports_incomplete_configuration(self):
        status, output = self.run_enroll("t3", TEST_LINK_DELAYED="1")
        self.assertEqual(status, 1, output)
        self.assertIn("environment linking is incomplete", output)
        self.assertNotIn("Enrolled T3", output)

    def test_failed_linking_running_service_preserves_work(self):
        _, runtime = self.seed_enrollment(desired=False, authenticated=False, linked=False)
        original_runtime = runtime.read_bytes()
        status, output = self.run_enroll("t3", TEST_LINK_INCOMPLETE="1")
        self.assertEqual(status, 1, output)
        self.assertIn("environment linking is incomplete", output)
        self.assertEqual(runtime.read_bytes(), original_runtime)
