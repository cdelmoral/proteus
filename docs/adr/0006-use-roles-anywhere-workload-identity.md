---
status: accepted
---

# Use a persistent IAM Roles Anywhere workload identity

Proteus uses a dedicated IAM Roles Anywhere certificate identity for unattended AWS access, extending ADR 0002's selected Host-Injected Credential model. A human IAM Identity Center session can obtain credentials for all of its assignments, including Production AWS Roles; selecting a development profile does not restrict that token. Human SSO caches and administrative host credentials therefore remain outside Proteus. Standard credential_process integration acquires temporary credentials on demand without a host broker or interactive SSO renewal.

The workload certificate and matching private key persist in 1Password and are explicitly enrolled after Provisioning or a rebuild. The guest user and root can extract the injected private key. The offline CA signing key belongs in a separate protected item, used only for host-side issuance; enrollment reads only the two selected workload fields. One-year workload certificates require annual host-side replacement and reenrollment. Reusing the workload identity restores access after rebuilding without reconstructing AWS trust, at the cost of explicit rotation and revocation for extracted copies.

Broad administration is allowed only in a dedicated development account whose production and cross-account isolation is enforced externally, beyond the agent's authority to remove. Local profile selection, account checks, and removable IAM restrictions cannot establish that boundary. Roles Anywhere trust must constrain the intended CA and workload identity. Deleting a VM or replacing a 1Password item does not revoke extracted keys or existing role sessions; stopping new issuance and addressing already issued sessions are separate operations.
