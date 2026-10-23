# AWS Credential Enrollment

This workflow starts with an existing workload identity. Arrange an externally isolated development AWS account, a dedicated offline CA, an IAM role, and a Roles Anywhere trust anchor and profile before enrollment. The role may have broad development administration, but production and other-account access must be prevented outside the agent's authority (for example by organization controls and externally managed trust). Enrollment checks the expected identity; it cannot prove production isolation. Never enroll a Production AWS Role or your human SSO session.

The AWS-side role trust must constrain the dedicated CA and workload certificate identity. Keep the CA signing key in a separate protected 1Password item, never in the workload item, VM, repository, or Provisioning inputs. Store a currently valid PEM workload certificate and its matching unencrypted PEM private key in distinct 1Password fields. Issue workload certificates for one year. The Roles Anywhere profile ARN identifies an AWS resource; it is distinct from the guest's default CLI profile.

Run `./configure`, retain your existing GitHub/Salesforce answers, and answer `true` to enable AWS. Supply these non-secret settings:

- `proteus_aws_account_id`: the 12-digit development account ID.
- `proteus_aws_role_arn`: the IAM role ARN in that account.
- `proteus_aws_region`: the Roles Anywhere region.
- `proteus_aws_trust_anchor_arn` and `proteus_aws_profile_arn`: resource ARNs matching the account and region.
- `proteus_aws_certificate_ref` and `proteus_aws_private_key_ref`: distinct `op://vault/item/field` workload references.

`proteus_aws_enabled` defaults to `false`. Blank answers retain saved settings; opting out retains the AWS values for later use. Enabled configuration must be complete and consistent before any configuration is saved. The current implementation supports the commercial `aws` partition.

After creating, starting, and provisioning the VM, run:

```bash
./enroll aws
# Or: ./enroll aws custom-instance
limactl shell --tty=false --start=false proteus aws sts get-caller-identity
```

Enrollment never manages the VM lifecycle. It checks the running VM and required tools before reading secrets. Both references are resolved on macOS before either credential is transferred. 1Password owns authentication, unlocking, and account selection. Transfer uses standard input without host secret files, secret arguments, forwarded credentials, or secret diagnostics. The guest never gains access to 1Password or the CA signing key.

The guest stages credentials under private `~/.local/share/proteus/aws/identity-*` directories (directories `0700`, files `0600`), validates certificate dates and key matching with OpenSSL, then verifies STS account and assumed-role identity through the candidate's credential_process. Candidate verification excludes ambient AWS variables and existing AWS profiles and shared credentials. Only successful verification atomically replaces `~/.aws/config`; failure preserves the previous active configuration and pair. Unrelated named profiles, default output settings, and shared credentials remain intact; competing identity sources in the owned default config are removed. A populated `[default]` in `~/.aws/credentials` must be moved to a named profile before enrollment because shared credentials override credential_process. Config formatting and comments may be normalized.

The default AWS profile uses an absolute `/usr/local/bin/aws_signing_helper` path and the selected certificate generation. AWS CLI and compatible SDKs acquire and refresh temporary role credentials on demand while trust, networking, and the certificate remain valid. `/usr/local/bin/aws` is available to noninteractive T3 processes without shell initialization or exported access keys. Explicit caller AWS credentials/profile variables still follow normal provider precedence during ordinary use; unset them to use the enrolled default. Enrollment does not restart T3. Existing SDK clients can retain an already issued session until normal refresh.

Reenrollment activates a new coherent generation. Older generations remain private so in-flight clients can finish using paths they have already loaded; delete obsolete `identity-*` directories only after such clients have finished. Provisioning updates tools and Managed Dotfiles without reading references or modifying AWS enrollment files.

For annual replacement, issue a new one-year certificate and matching key on the trusted host, update the selected workload fields together, and run `./enroll aws` before expiry. Keep the CA key separate throughout issuance and clean up protected host temporary material. After expiry, issue a replacement and reenroll using the same AWS trust resources. Failed rotation leaves the previous setup active but cannot extend an expired certificate. After rebuilding, provision and reenroll the existing workload references; stop/start retains credentials.

For compromise, use a trusted administrative host identity to disable the Roles Anywhere profile or trust anchor, or revoke the certificate through an applicable Roles Anywhere CRL, to stop new issuance. Separately revoke active sessions for the IAM role and assess already performed actions; disabling issuance alone does not invalidate existing temporary sessions immediately. See AWS's [Roles Anywhere revocation guidance](https://docs.aws.amazon.com/rolesanywhere/latest/userguide/trust-model.html) and [revoking role sessions](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_revoke-sessions.html). Rotate the compromised workload key and update/reenroll the selected item; a compromised CA requires replacing trust as well. Deleting the VM or updating 1Password does not invalidate extracted credentials. Do not use guest administration as proof that emergency isolation is enforced.
