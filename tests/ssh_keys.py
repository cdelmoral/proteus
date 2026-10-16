"""Generate disposable SSH keys for enrollment tests."""

import subprocess


def generate_signing_key(directory, name="signing-key", passphrase=""):
    path = directory / name
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", passphrase, "-f", str(path)],
        check=True, capture_output=True, text=True, timeout=10,
    )
    return path
