"""Exercise Git and GitHub CLI credentials without an interactive shell or network."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from ssh_keys import generate_signing_key


ROOT = Path(__file__).resolve().parents[1]
GH = shutil.which("gh", path=os.defpath)


@unittest.skipUnless(GH and shutil.which("git") and shutil.which("ssh-keygen"),
                     "Git, GitHub CLI, and OpenSSH are required")
class GitHubCredentialsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        shutil.copytree(ROOT / "dotfiles/home", self.home, dirs_exist_ok=True)
        self.bin = self.home / "test-bin"
        self.bin.mkdir()
        # Only enrollment validation is simulated. Credential lookup uses the
        # real GitHub CLI with dummy tokens and never contacts the network.
        gh = self.bin / "gh"
        gh.write_text(
            "#!/bin/sh\n"
            'if [ "$1 $2" = "auth status" ]; then\n'
            '  [ "$GH_TOKEN" != "rejected-token" ]; exit $?\n'
            'fi\n'
            f'exec "{GH}" "$@"\n'
        )
        gh.chmod(0o755)
        wrapper = self.home / ".local/bin/gh"
        if wrapper.exists():
            # Relocate the packaged binary to the simulated enrollment checker.
            # The production wrapper's credential loading runs unchanged.
            wrapper.write_text(wrapper.read_text().replace("/usr/bin/gh", str(gh)))
        self.system_bin = self.home / "test-system-bin"
        self.system_bin.mkdir()
        # Provisioning exposes this same wrapper on the system PATH, which
        # does not require ~/.local/bin or shell startup files.
        (self.system_bin / "gh").symlink_to(wrapper)
        self.environment = {
            key: value for key, value in os.environ.items()
            if key not in ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN")
            and not key.startswith("GIT_")
        }
        self.environment.update(
            HOME=str(self.home),
            PATH=f"{self.system_bin}:{self.bin}:/usr/bin:/bin",
            XDG_CONFIG_HOME=str(self.home / ".config"),
            GH_CONFIG_DIR=str(self.home / ".config/gh"),
            GIT_CONFIG_NOSYSTEM="1",
            GIT_TERMINAL_PROMPT="0",
        )
        self.token = self.home / ".local/share/proteus/secrets/github-token"
        self.fixture_key = generate_signing_key(self.home)
        self.signing_key = self.token.parent / "git-signing-key"

    def enroll(self, token="fixture-token", key=None):
        result = subprocess.run(
            [str(self.home / ".local/bin/proteus-enroll-github")],
            input=f"{token}\n{key or self.fixture_key.read_text()}",
            env=self.environment, capture_output=True, text=True, timeout=10,
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

    def gh(self, *arguments, **environment):
        return subprocess.run(
            ["gh", *arguments], env={**self.environment, **environment},
            capture_output=True, text=True, timeout=10,
        )

    def test_background_gh_reads_enrolled_token_on_system_path(self):
        self.enroll()
        result = self.gh("auth", "token", "--hostname", "github.com")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "fixture-token")
        self.assertEqual(result.stderr, "")

    def test_background_gh_reads_rotated_token_without_service_restart(self):
        self.enroll()
        self.enroll("rotated-token")
        result = self.gh("auth", "token", "--hostname", "github.com")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "rotated-token")

    def test_explicit_gh_token_overrides_enrolled_token(self):
        self.enroll()
        for variable in ("GH_TOKEN", "GITHUB_TOKEN"):
            with self.subTest(variable=variable):
                result = self.gh("auth", "token", "--hostname", "github.com", **{variable: "override-token"})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), "override-token")

    def test_rejected_replacement_token_is_validated_instead_of_enrolled_token(self):
        self.enroll()
        original_key = self.signing_key.read_bytes()
        original_config = (self.home / ".gitconfig.local").read_bytes()
        replacement = generate_signing_key(self.home, "replacement-key")
        result = subprocess.run(
            [str(self.home / ".local/bin/proteus-enroll-github")],
            input=f"rejected-token\n{replacement.read_text()}",
            env=self.environment, capture_output=True, text=True, timeout=10,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("GitHub rejected", result.stderr)
        self.assertEqual(self.token.read_text(), "fixture-token")
        self.assertEqual(self.signing_key.read_bytes(), original_key)
        self.assertEqual((self.home / ".gitconfig.local").read_bytes(), original_config)
        self.assertEqual(list(self.token.parent.glob(".github-enrollment.*")), [])
        self.assertNotIn("rejected-token", result.stdout + result.stderr)

    def test_background_commit_signing_preserves_identity_and_survives_reprovisioning(self):
        local_config = self.home / ".gitconfig.local"
        local_config.write_text(
            '[user]\n name = Fixture User\n email = fixture@example.com\n signingKey = old-key\n'
            '[gpg]\n format = openpgp\n[gpg "ssh"]\n program = /missing/host/signer\n'
            '[commit]\n gpgSign = false\n[fetch]\n prune = true\n'
        )
        self.enroll()
        self.enroll()  # Repeating enrollment must preserve identity and preferences.
        shutil.copy2(ROOT / "dotfiles/home/.gitconfig", self.home / ".gitconfig")
        for name, expected in (("user.name", "Fixture User"), ("user.email", "fixture@example.com"),
                               ("fetch.prune", "true")):
            result = subprocess.run(
                ["git", "config", "--get", name], env=self.environment,
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.stdout.strip(), expected)
        for path in (self.token, self.signing_key, self.signing_key.with_suffix(".pub")):
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.token.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.signing_key.read_bytes(), self.fixture_key.read_bytes())
        self.assertEqual(self.signing_key.with_suffix(".pub").read_text().split()[:2],
                         self.fixture_key.with_suffix(".pub").read_text().split()[:2])

        repository = self.home / "repository"
        repository.mkdir()
        subprocess.run(["git", "init", "-q", str(repository)], check=True,
                       env=self.environment, capture_output=True, timeout=10)
        # Simulate a background service with no terminal or SSH agent.
        environment = {key: value for key, value in self.environment.items()
                       if key not in ("SSH_AUTH_SOCK", "SSH_AGENT_PID")}
        commit = subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "Signed fixture"], cwd=repository,
            env=environment, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(commit.returncode, 0, commit.stderr)
        allowed_signers = self.home / "allowed_signers"
        allowed_signers.write_text(f"fixture@example.com {self.signing_key.with_suffix('.pub').read_text()}")
        verified = subprocess.run(
            ["git", "-c", f"gpg.ssh.allowedSignersFile={allowed_signers}", "verify-commit", "HEAD"],
            cwd=repository, env=environment, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(verified.returncode, 0, verified.stderr)

    def test_invalid_or_encrypted_key_preserves_existing_credentials_and_config(self):
        self.enroll()
        original = {path: path.read_bytes() for path in (
            self.token, self.signing_key, self.signing_key.with_suffix(".pub"),
            self.home / ".gitconfig.local",
        )}
        encrypted = generate_signing_key(self.home, "encrypted-key", passphrase="fixture-passphrase")
        for key in ("", "invalid private key", encrypted.read_text()):
            with self.subTest(key_type="encrypted" if key.startswith("-----") else "missing or malformed"):
                result = subprocess.run(
                    [str(self.home / ".local/bin/proteus-enroll-github")],
                    input=f"replacement-token\n{key}", env=self.environment,
                    capture_output=True, text=True, timeout=10,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("unencrypted OpenSSH private signing key", result.stderr)
                self.assertNotIn("replacement-token", result.stdout + result.stderr)
                if key:
                    self.assertNotIn(key, result.stdout + result.stderr)
                for path, content in original.items():
                    self.assertEqual(path.read_bytes(), content)
                self.assertEqual(list(self.token.parent.glob(".github-enrollment.*")), [])

    def test_reenrollment_rotates_key_and_token(self):
        self.enroll()
        replacement = generate_signing_key(self.home, "replacement-key")
        self.enroll("rotated-token", key=replacement.read_text())
        self.assertEqual(self.signing_key.read_bytes(), replacement.read_bytes())
        self.assertEqual(self.token.read_text(), "rotated-token")
        self.assertEqual(list(self.token.parent.glob(".github-enrollment.*")), [])

    def test_missing_enrolled_token_preserves_native_gh_behavior_and_exit_status(self):
        for home in (self.home, self.home / "other-user"):
            with self.subTest(home=home):
                version = self.gh("--version", HOME=str(home))
                self.assertEqual(version.returncode, 0, version.stderr)
                self.assertIn("gh version", version.stdout)
                result = self.gh("auth", "token", "--hostname", "github.com", HOME=str(home))
                native = subprocess.run(
                    [GH, "auth", "token", "--hostname", "github.com"],
                    env={**self.environment, "HOME": str(home)},
                    capture_output=True, text=True, timeout=10,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual((result.returncode, result.stdout, result.stderr),
                                 (native.returncode, native.stdout, native.stderr))

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
