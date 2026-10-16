---
status: accepted
---

# Enroll a persistent Git signing key from 1Password

GitHub Credential Enrollment requires references for both the GitHub token and a persistent Git signing key held in 1Password, so one explicit enrollment command restores access and signing after a rebuild without another GitHub signing-key registration. The trusted macOS host resolves the references and transfers the selected credentials explicitly, extending ADR 0002 and superseding ADR 0001's SSH-key-import restriction only for this signing credential; the guest gains no access to the source vault or host SSH agent. Reusing a key across rebuilds means deleting a VM does not invalidate any extracted copies; replacing the signing identity requires key rotation and an updated GitHub registration.

Enrollment configures signing while preserving the existing Git name, email, and unrelated configuration. It derives the public key from the supplied private key as part of installation, retains the existing token validation, and avoids additional commit tests or GitHub signing-key registration checks to keep setup simple; GitHub registration remains a separate one-time user task.
