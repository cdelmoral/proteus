# Allow selected Host-Injected Credentials

Proteus trusts the macOS host to select and inject a credential explicitly, while the guest remains unable to access the source credential store or unrelated host credentials. GitHub Credential Enrollment resolves one configured 1Password reference on the host and streams the token to the guest through standard input. It does not use command arguments, environment forwarding, host files, mounts, or agent forwarding for the token.

We rejected the stricter rule that every credential must be created inside the guest. That rule prevents the user's 1Password item from remaining the source of truth and forces manual GitHub authentication after each rebuild. The selected token becomes guest data after enrollment, so the guest user and guest root can read it.

Credential Enrollment remains an explicit step after Provisioning. Provisioning continues to install only the Development Baseline and never resolves or installs credentials. This decision supersedes only the clauses in both ADR 0001 files that require all Credential Enrollment to remain inside Proteus or be VM-local. Their decisions about host mounts, SSH credentials, agent forwarding, Lima SSH, and Ansible remain in effect.

ADR 0005 extends GitHub Credential Enrollment to inject a selected Git signing key alongside the token, making an explicit exception to the retained SSH-key-import restriction for this signing credential.
