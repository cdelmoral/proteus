"""Exercise the Salesforce CLI launcher without an interactive shell or network."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
# Provisioning installs the official archive here, outside the user PATH.
CLI_DIR = ".local/share/proteus/salesforce-cli/current/bin"


class SalesforceCliTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        shutil.copytree(ROOT / "dotfiles/home", self.home, dirs_exist_ok=True)
        self.log = self.home / "sf-calls.jsonl"
        # Only the archive runtime and CLI are simulated. The
        # launcher runs unchanged.
        self.write_command(self.home / CLI_DIR / "node", """
import os, sys
os.environ['TEST_RUNTIME'] = 'bundled-node'
assert sys.argv[1] == "--no-deprecation"
os.execv(sys.argv[2], sys.argv[2:])
""")
        self.write_command(self.home / CLI_DIR / "run.js", """
import json, os, sys
names = ('SF_USE_GENERIC_UNIX_KEYCHAIN', 'SF_DISABLE_TELEMETRY', 'SF_AUTOUPDATE_DISABLE', 'SF_DISABLE_AUTOUPDATE', 'TEST_RUNTIME')
with open(os.environ['TEST_LOG'], 'a') as log:
    log.write(json.dumps({'args': sys.argv[1:], 'env': {name: os.environ.get(name) for name in names}}) + '\\n')
if sys.argv[1:] == ['fixture-child']:
    import subprocess
    sys.exit(subprocess.call(['node', '--version'], timeout=10))
print('@salesforce/cli/2.0.0 linux-arm64 node-v24.20.0')
""")
        self.system_bin = self.home / "test-system-bin"
        self.system_bin.mkdir()
        # Provisioning exposes this same launcher on the system PATH, which
        # does not require ~/.local/bin or shell startup files.
        (self.system_bin / "sf").symlink_to(self.home / ".local/bin/sf")
        self.environment = {
            "HOME": str(self.home),
            "PATH": f"{self.system_bin}:/usr/bin:/bin",
            "TEST_LOG": str(self.log),
        }

    def write_command(self, path, body):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"#!{sys.executable}\n{body}")
        path.chmod(0o755)

    def sf(self, *arguments, **environment):
        return subprocess.run(
            ["sf", *arguments], env={**self.environment, **environment},
            capture_output=True, text=True, timeout=10,
        )

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_background_sf_runs_installed_cli_from_system_path(self):
        result = self.sf("--version")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("@salesforce/cli/", result.stdout)
        self.assertEqual([call["args"] for call in self.calls()], [["--version"]])

    def test_launcher_always_uses_file_keychain_without_telemetry(self):
        for inherited in ({}, {"SF_USE_GENERIC_UNIX_KEYCHAIN": "false", "SF_DISABLE_TELEMETRY": "false", "SF_AUTOUPDATE_DISABLE": "false", "SF_DISABLE_AUTOUPDATE": "false"}):
            with self.subTest(inherited=inherited):
                result = self.sf("org", "list", "--json", **inherited)
                self.assertEqual(result.returncode, 0, result.stderr)
                call = self.calls()[-1]
                self.assertEqual(call["args"], ["org", "list", "--json"])
                self.assertEqual(call["env"], {
                    "SF_USE_GENERIC_UNIX_KEYCHAIN": "true",
                    "SF_DISABLE_TELEMETRY": "true",
                    "TEST_RUNTIME": "bundled-node",
                    "SF_AUTOUPDATE_DISABLE": "true",
                    "SF_DISABLE_AUTOUPDATE": "true",
                })

    def test_project_node_does_not_control_cli_or_child_path(self):
        for selection in ('20.19.0', '22.16.0', 'missing'):
            with self.subTest(selection=selection):
                project = self.home / selection
                project.mkdir()
                (project / '.node-version').write_text(selection)
                binary = project / 'bin'
                binary.mkdir()
                node = binary / 'node'
                node.write_text('#!/bin/sh\n' + ('exit 42\n' if selection == 'missing' else f'echo {selection}\n'))
                node.chmod(0o755)
                env = {**self.environment, 'PATH': f'{binary}:{self.environment["PATH"]}'}
                for args in (['--version'], ['org', 'list', '--target-org', 'name with spaces', '', '--json']):
                    result = subprocess.run(['sf', *args], env=env, cwd=project,
                                            capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(self.calls()[-1]['args'], args)
                child = subprocess.run(['sf', 'fixture-child'], env=env, cwd=project,
                                       capture_output=True, text=True, timeout=10)
                self.assertEqual(child.returncode, 42 if selection == 'missing' else 0)
                if selection != 'missing':
                    self.assertEqual(child.stdout.strip(), selection)

    def test_launcher_propagates_cli_failure(self):
        cli = self.home / CLI_DIR / "run.js"
        cli.write_text(cli.read_text() + "sys.exit(7)\n")
        self.assertEqual(self.sf("--version").returncode, 7)


if __name__ == "__main__":
    unittest.main()
