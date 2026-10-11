"""Exercise Git's real credential lookup without an interactive shell or network."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
GH = shutil.which("gh")


@unittest.skipUnless(GH and shutil.which("git"), "Git and GitHub CLI are required")
class GitHubCredentialsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        shutil.copytree(ROOT / "dotfiles/home", self.home, dirs_exist_ok=True)
        self.bin = self.home / "test-bin"
        self.bin.mkdir()
        # Enrollment validation is the only network boundary. Git setup and
        # credential lookup use the real GitHub CLI with a dummy token.
        gh = self.bin / "gh"
        gh.write_text(
            "#!/bin/sh\n"
            'if [ "$1 $2" = "auth status" ]; then exit 0; fi\n'
            f'exec "{GH}" "$@"\n'
        )
        gh.chmod(0o755)
        self.environment = {
            key: value for key, value in os.environ.items()
            if key not in ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN")
            and not key.startswith("GIT_")
        }
        self.environment.update(
            HOME=str(self.home),
            PATH=f"{self.bin}:/usr/bin:/bin",
            XDG_CONFIG_HOME=str(self.home / ".config"),
            GH_CONFIG_DIR=str(self.home / ".config/gh"),
            GIT_CONFIG_NOSYSTEM="1",
            GIT_TERMINAL_PROMPT="0",
        )
        self.token = self.home / ".local/share/proteus/secrets/github-token"

    def enroll(self, token="fixture-token"):
        result = subprocess.run(
            [str(self.home / ".local/bin/proteus-enroll-github")],
            input=token, env=self.environment, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(token, result.stdout + result.stderr)

    def credential(self, host="github.com", **environment):
        return subprocess.run(
            ["git", "credential", "fill"],
            input=f"protocol=https\nhost={host}\n\n",
            env={**self.environment, **environment},
            capture_output=True, text=True, timeout=10,
        )

    def test_background_git_reads_enrolled_token(self):
        managed_config = (self.home / ".gitconfig").read_bytes()
        self.enroll()
        self.assertEqual((self.home / ".gitconfig").read_bytes(), managed_config)
        result = self.credential()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("password=fixture-token\n", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_reprovisioning_preserves_background_git_access(self):
        self.enroll()
        shutil.copy2(ROOT / "dotfiles/home/.gitconfig", self.home / ".gitconfig")
        result = self.credential()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("password=fixture-token\n", result.stdout)

    def test_running_process_reads_rotated_token_instead_of_inherited_token(self):
        self.enroll()
        self.enroll("rotated-token")
        result = self.credential(GH_TOKEN="stale-inherited-token")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("password=rotated-token\n", result.stdout)
        self.assertNotIn("stale-inherited-token", result.stdout + result.stderr)

    def test_gist_uses_enrolled_github_token(self):
        self.enroll()
        result = self.credential("gist.github.com")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("password=fixture-token\n", result.stdout)

    def test_missing_token_and_other_hosts_do_not_disclose_credentials(self):
        self.enroll()
        other_host = self.credential("example.invalid")
        self.assertNotEqual(other_host.returncode, 0)
        self.assertNotIn("fixture-token", other_host.stdout + other_host.stderr)
        self.token.unlink()
        missing = self.credential()
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("terminal prompts disabled", missing.stderr)
        self.assertNotIn("fixture-token", missing.stdout + missing.stderr)


if __name__ == "__main__":
    unittest.main()
