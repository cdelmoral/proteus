"""Exercise reference configuration without accessing 1Password."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ConfigureTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.environment = {**os.environ, "HOME": str(self.directory),
                            "XDG_CONFIG_HOME": str(self.directory / "config")}
        self.configuration = self.directory / "config/proteus/config"

    def configure(self, responses):
        return subprocess.run(
            [str(ROOT / "configure")], input=responses, env=self.environment,
            capture_output=True, text=True, timeout=10,
        )

    def test_saves_both_references_with_examples_and_accepts_current_values(self):
        # References are data, including spaces and shell metacharacters.
        token = "op://vault/GitHub/token"
        signing_key = "op://vault/Signing $(touch unexpected)/private key"
        result = self.configure(f"{token}\n{signing_key}\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("e.g. op://vault/item/entry", result.stdout)
        self.assertIn("e.g. op://vault/item/private key", result.stdout)
        expected = (f"github_token_1password_reference={token}\n"
                    f"git_signing_key_1password_reference={signing_key}\n"
                    "salesforce_login_url=https://login.salesforce.com\n")
        self.assertEqual(self.configuration.read_text(), expected)
        self.assertEqual(self.configuration.stat().st_mode & 0o777, 0o600)
        repeated = self.configure("\n\n")
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertIn(f"[{signing_key}]", repeated.stdout)
        self.assertEqual(self.configuration.read_text(), expected)
        self.assertFalse((ROOT / "unexpected").exists())

    def test_token_only_configuration_can_be_upgraded(self):
        self.configuration.parent.mkdir(parents=True)
        self.configuration.write_text("github_token_1password_reference=op://vault/GitHub/token\n")
        result = self.configure("\nop://vault/Signing/private key\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.configuration.read_text(),
                         "github_token_1password_reference=op://vault/GitHub/token\n"
                         "git_signing_key_1password_reference=op://vault/Signing/private key\n"
                         "salesforce_login_url=https://login.salesforce.com\n")

    def test_adding_signing_key_preserves_salesforce_url_and_unrelated_config(self):
        self.configuration.parent.mkdir(parents=True)
        self.configuration.write_text(
            "github_token_1password_reference=op://vault/GitHub/token\n"
            "salesforce_login_url=https://example.my.salesforce.com\n"
            "unrelated_setting=keep-me\n"
        )
        result = self.configure("\nop://vault/Signing/private key\n\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[https://example.my.salesforce.com]", result.stdout)
        self.assertEqual(sorted(self.configuration.read_text().splitlines()), [
            "git_signing_key_1password_reference=op://vault/Signing/private key",
            "github_token_1password_reference=op://vault/GitHub/token",
            "salesforce_login_url=https://example.my.salesforce.com",
            "unrelated_setting=keep-me",
        ])

    def test_missing_required_reference_does_not_save_partial_configuration(self):
        for responses in ("\n", "op://vault/GitHub/token\n\n"):
            with self.subTest(responses=responses):
                result = self.configure(responses)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("reference is required", result.stderr)
                self.assertFalse(self.configuration.exists())

    def test_interrupted_reconfiguration_preserves_previous_references(self):
        self.assertEqual(self.configure("op://vault/old/token\nop://vault/old/private key\n").returncode, 0)
        original = self.configuration.read_bytes()
        result = self.configure("op://vault/new/token\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.configuration.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
