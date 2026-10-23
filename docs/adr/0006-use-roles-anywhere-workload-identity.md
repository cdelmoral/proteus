---
status: accepted
---

# Use a persistent IAM Roles Anywhere workload identity

Proteus uses a dedicated IAM Roles Anywhere certificate identity for unattended AWS access, extending ADR 0002's selected Host-Injected Credential model. A human IAM Identity Center session can obtain credentials for all of its assignments, including Production AWS Roles; selecting a development profile does not restrict that token. Human SSO caches and administrative host credentials therefore remain outside Proteus. Standard credential_process integration acquires temporary credentials on demand without a host broker or interactive SSO renewal.

The workload certificate and matching private key persist in 1Password and are explicitly enrolled after Provisioning or a rebuild. The guest user and root can extract the injected private key. The offline CA signing key belongs in a separate protected item, used only for host-side issuance; enrollment reads only the two selected workload fields. One-year workload certificates require annual host-side replacement and reenrollment. Reusing the workload identity restores access after rebuilding without reconstructing AWS trust, at the cost of explicit rotation and revocation for extracted copies.

Broad administration is allowed only in a dedicated development account whose production and cross-account isolation is enforced externally, beyond the agent's authority to remove. Local profile selection, account checks, and removable IAM restrictions cannot establish that boundary. Roles Anywhere trust must constrain the intended CA and workload identity. Deleting a VM or replacing a 1Password item does not revoke extracted keys or existing role sessions; stopping new issuance and addressing already issued sessions are separate operations.

Host setup and replacement use `./aws-setup`; replacement is explicit through
`--renew`, never a side effect of retrying initial setup. Renewal requires the
original protected CA and compatible existing AWS resources and makes no AWS
mutations. It accepts an expired old workload certificate, verifies a fresh
one-year pair against AWS before offering the selected item update, and reads
both stored fields back. Lost write acknowledgments require item inspection;
external writes are not transactional with guest enrollment. The guest's existing
transactional enrollment remains the sole activation boundary, preserving its
previous generation on failure without restarting T3. Restoring tools and
non-secret settings after a rebuild grants no access until explicit reenrollment.

Setup emits a non-secret YAML summary; `./configure` records its values in the
host's key=value configuration. Neither command transfers CA signing material or
host administrative credentials to the guest. Temporary session refresh depends
on valid certificates, policies/trust and network; it is not certificate renewal.
See the [operating procedure](../aws-setup.md) and the
[acceptance record](../testing.md#aws-acceptance-record-2026-10-23) for validation
scope. Simulated lifecycle checks do not establish real AWS acceptance or the
externally maintained production-isolation boundary.
