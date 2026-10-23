# Host AWS workload setup

`./aws-setup` creates a dedicated IAM Roles Anywhere workload identity on the
trusted host. It never contacts Lima or enrolls a guest. Provisioning and AWS
Credential Enrollment remain separate operations.

## Prerequisites and isolation

Install Python 3.9 or newer, OpenSSL (including `genpkey`), AWS CLI v2,
1Password CLI v2 (`op`), and the official macOS `aws_signing_helper` on the host
PATH. Obtain the helper from AWS's [credential helper documentation](https://docs.aws.amazon.com/rolesanywhere/latest/userguide/credential-helper.html)
and verify the published checksum. Sign in to 1Password normally; its CLI handles
unlocking and account selection. Create the destination vaults beforehand.

Use a dedicated development account whose isolation from production and other
accounts is enforced outside the workload administrator's control. An account
identity check, the selected CLI profile, or a policy the administrator can remove
does not establish this boundary. Review organization controls and cross-account
trust/escalation paths separately. Building organization-wide isolation is out of
scope. Do not proceed in a production account.

Select an existing host administrative AWS CLI profile explicitly. It needs STS
identity lookup, IAM role listing/creation and policy attachment, and Roles
Anywhere trust-anchor/profile listing, creation and profile lookup. It may use
human SSO: authenticate on the host first, for example with
`aws sso login --profile development-admin`. Human credentials and SSO caches
never enter Proteus. Setup ignores ambient AWS credential and endpoint variables;
only `AWS_CONFIG_FILE` and `AWS_SHARED_CREDENTIALS_FILE` are retained for locating
the explicitly selected administrative profile. Profile configuration itself is
trusted host input; do not use profiles with custom cloud endpoints.

## Run setup

```bash
./aws-setup --account-id 123456789012 \
  --admin-profile development-admin --region us-east-1
```

The default dedicated resource name and workload certificate CN are `proteus`.
`--name` selects another name (1–48 letters, numbers, underscores or hyphens).
Use the same account, region, name and item references for retries. This command
supports the commercial `aws` partition. Run one setup at a time for an identity.

1. Setup verifies the administrative identity's account before any AWS or vault
   mutation. Confirm that external isolation controls are in place.
2. Enter the intended workload reference, such as
   `op://Development/Proteus AWS/certificate`. Setup uses sibling fields
   `certificate` and `private key`; sectioned references are not supported.
3. Enter a separate protected CA item reference, such as
   `op://Protected/Proteus AWS CA/certificate`. Restrict that vault/item to trusted
   host operators. Setup cannot configure or prove 1Password access controls.
4. Accept creation of the workload item, or update of an existing empty item.
   Reference selection always precedes the storage offer. An existing complete
   pair is validated and reused without updates. Setup does not replace an
   existing certificate or rotate a key unless `--renew` is explicitly supplied.
5. If the CA item is absent, explicitly accept creation. Its ten-year self-signed
   EC P-256 CA has certificate-signing/CRL-signing usage and a path-length limit
   of zero. Setup stores it in the protected item and reads it back before any
   AWS resource creation. Existing CAs are validated and reused; missing keys,
   invalid certificates, ambiguous/archived items and mismatched identities stop
   setup. An existing workload with a missing CA stops setup rather than
   generating a replacement CA.
6. Setup signs a matching EC P-256 workload pair for 365 days, with X.509v3
   `CA:FALSE`, digital-signature key usage and SHA-256 signing. The CA must remain
   valid throughout issuance. Both workload fields are written together in one
   item operation and read back before AWS changes. Existing unrelated item
   fields are preserved. Existing items must be Secure Notes; other categories
   are rejected, since 1Password JSON-template edits can overwrite passkeys.
7. Setup creates the trust anchor, dedicated role and Roles Anywhere profile.
   The role grants AdministratorAccess and trusts the Roles Anywhere service
   with `AssumeRole`, `SetSourceIdentity` and `TagSession`, constrained by the
   exact trust-anchor ARN, account and workload CN. The enabled Roles Anywhere
   profile lists only this role and requests one-hour sessions. Existing
   resources are reused only when compatible; differing or disabled resources
   are rejected without changing their trust, CA or profile. Reattaching the
   administrator policy repairs retries after role creation.
8. Setup verifies the workload through the host helper and STS, checking the
   exact account and assumed role. This verification uses a private temporary
   default profile with `credential_process`, an empty credentials file, no
   ambient AWS variables and no instance metadata credentials. It cannot pass
   by falling back to the administrative profile. IAM propagation delays can
   cause initial verification to fail: retry with the same references.

During initial setup, declining storage exits unsuccessfully before issuance or
cloud changes. Renewal verifies a temporary candidate before its update offer;
declining that offer discards the candidate and preserves the stored pair. Partial
external failure is reported as incomplete and does not emit enrollment settings.
Existing pairs/resources are retained so the same command can resume. Already
successful AWS or vault writes are not rolled back. If a write's result is lost,
inspect the selected item/resource before retrying; setup lists existing items
rather than interpreting an authentication failure as an absent item. If duplicate
names exist, select a unique item ID or resolve duplicate AWS names manually.
A damaged workload pair requires restoration or a separately selected empty item;
setup never silently repairs it by replacing the private key.

## Settings handed to configuration

Only after successful workload verification, setup prints the following YAML
mapping, using JSON-quoted strings (valid YAML). It writes no repository,
Provisioning or enrollment configuration and never changes VM lifecycle:

```yaml
proteus_aws_enabled: true
proteus_aws_account_id: "123456789012"
proteus_aws_role_arn: "arn:aws:iam::123456789012:role/proteus"
proteus_aws_region: "us-east-1"
proteus_aws_trust_anchor_arn: "arn:aws:rolesanywhere:us-east-1:123456789012:trust-anchor/ANCHOR_ID"
proteus_aws_profile_arn: "arn:aws:rolesanywhere:us-east-1:123456789012:profile/PROFILE_ID"
proteus_aws_certificate_ref: "op://VAULT_ID/WORKLOAD_ITEM_ID/certificate"
proteus_aws_private_key_ref: "op://VAULT_ID/WORKLOAD_ITEM_ID/private key"
```

The resource ARNs identify the AWS-side trust anchor and Roles Anywhere profile;
that profile is distinct from a guest's default AWS CLI profile. Run `./configure`,
retain the GitHub/Salesforce answers, answer `true` for AWS,
and paste each emitted value into the prompt with the matching key (without YAML
quotes). Host configuration at `${XDG_CONFIG_HOME:-$HOME/.config}/proteus/config`
is **key=value**, not YAML: do not redirect or append setup output to that file.
Setup output also contains prompts/status text; its final YAML mapping is only a
non-secret summary. `./configure` validates and saves the complete group,
preserving unrelated settings. See [AWS Credential Enrollment](./aws-enrollment.md).
The protected CA reference is deliberately absent. Only the two selected workload fields belong in
enrollment. Keep the complete workload pair in 1Password after a VM rebuild,
then explicitly reenroll it; rebuilding does not require new AWS trust.

## Custody, failure recovery and lifecycle

Certificate/key material is handled in process memory, private host temporary
files (directory mode 0700, file mode 0600), and 1Password stdin/stdout pipes.
Private keys are never command arguments, forwarded environment variables,
repository files, or terminal output. Subprocess diagnostics are suppressed
because they may echo secrets. Temporary files are removed on success, exceptions,
Ctrl-C and SIGTERM. An uncatchable termination or host crash can leave material
under the host temporary directory as `proteus-aws-*`; remove it securely after
checking that no setup is running. File removal does not guarantee physical disk
erasure; trust the host's disk encryption and temporary-storage protections.

Preserve a recoverable, access-controlled backup of the CA item and its matching
certificate/private key. Restore the same item after loss or accidental archival.
Never substitute a newly generated CA into an existing trust anchor as a retry.
If the CA is irrecoverable, plan an explicit trust migration with a new identity;
existing workload credentials may still function until certificate expiry or
revocation, but no replacement can be signed with the lost key.

## Annual replacement and expiration recovery

Schedule replacement before the one-year workload certificate expires. Use the
same account, region, name, administrative profile and item references as setup:

```bash
./aws-setup --renew --account-id 123456789012 \
  --admin-profile development-admin --region us-east-1
./enroll aws
# For a custom VM: ./enroll aws custom-instance
limactl shell --tty=false --start=false proteus aws sts get-caller-identity
```

1. Authenticate the selected administrative host profile and unlock 1Password.
   Renewal checks its account and asks for external-isolation confirmation.
2. Select the existing workload and separate protected CA references. Renewal
   requires a complete matching workload pair signed by that CA, with the expected
   CN. Expiration of the old workload is permitted; damaged/mismatched material
   requires restoration from backup first. The CA must be valid now and have at
   least 365 days remaining. An expired or nearly expired CA needs a planned trust
   migration; `--renew` never replaces it.
3. The host issues a fresh 365-day certificate and new private key, checks existing
   AWS resources for compatibility, and verifies the candidate's exact account/role
   using the helper and STS before offering the item update. Renewal performs no
   AWS mutations, policy repairs or resource creation. Missing, disabled or changed
   resources require administrative recovery first.
4. Accept the update to the selected workload item. Both fields are submitted in
   one operation and read back. The CA item, trust anchor, role and Roles Anywhere
   profile remain the same. Unrelated workload fields are preserved. Refusal or
   pre-write failure leaves the stored pair intact. Concurrent item editing or
   issuance for the same identity is unsupported.
5. Check successful completion. If item editing/read-back fails or the connection
   is lost, inspect both selected fields in 1Password before retrying. A completed
   external write cannot be rolled back reliably; the item may already contain
   the new pair. An ordinary setup retry validates/reuses that pair; another
   `--renew` deliberately issues another replacement.
6. Retain the existing `./configure` settings when references/ARNs are unchanged;
   otherwise update them from the summary using `./configure`. Explicitly reenroll
   the running, provisioned guest. Setup never changes guest credentials. Failed
   reenrollment leaves its previous generation active; correct the reported
   problem and rerun enrollment. Verify STS and an AWS call from the T3 agent.
   No T3 restart is required; existing SDK clients refresh on their own schedule.

After workload expiration, follow the same `--renew` and enrollment steps using
host administrative access and the original CA. Ordinary setup and enrollment
reject expired candidates; renewal alone permits the expired **old** certificate.
Preservation of an expired guest generation does not make it usable. A failed
replacement cannot extend certificate validity. Temporary role credentials can be
reacquired on demand only while the workload certificate, AWS trust/policies and
network remain valid; annual certificate replacement is an explicit operation.

## Rebuild checklist

1. Preserve the selected workload pair and protected CA backup in 1Password, plus
   the non-secret host settings. Deleting a VM does not revoke copied keys.
2. Recreate/start the VM from its VM Definition and run `./provision [instance]`.
   This restores tools and Managed Dotfiles, without credentials or vault access.
3. Restore/retain host settings through `./configure`; keep the same account, role,
   trust-anchor/profile ARNs and workload references. Do not rerun initial trust
   setup. If the certificate expired, renew it on the host first.
4. Run `./enroll aws [instance]`, verify the expected STS identity, then test an AWS
   call through T3. VM stop/start retains enrollment; rebuilding requires explicit
   reenrollment. Provisioning an existing guest preserves its active generation.

## Emergency revocation

From a trusted administrative host outside Proteus, disable the Roles Anywhere
trust anchor/profile or remove the role trust to stop new issuance, and address already issued role sessions
using AWS's [role-session revocation procedure](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_revoke-sessions.html).
Imported CRLs can revoke a specific certificate; AWS does not use OCSP or CRL
URLs for these checks. Replacing the vault item, deleting the VM, or stopping new
issuance does not by itself immediately invalidate existing sessions or extracted
key copies. A compromised CA affects every certificate it signed and requires
explicit trust replacement. Keep new issuance disabled until compromised workload
certificates have been revoked (or compromised CA trust replaced); otherwise old
extracted keys can acquire new sessions when issuance is reenabled. Review the
incident and externally verify containment. After revoking the compromised
certificate or migrating compromised CA trust, an external administrator can
reenable the intended profile/trust for clean issuance and reenrollment. `--renew`
requires enabled resources and cannot verify a replacement while issuance is
disabled. A CA compromise needs a separately planned new CA/trust identity rather
than ordinary renewal. Setup itself performs no revocation
operations. Role-session deny policies within the workload administrator's control
are not a substitute for externally enforced containment.

## Validation and primary references

Run `python3 -B -m unittest discover -s tests -p 'test_aws_*.py'`. Tests execute
`./aws-setup` with isolated homes, simulated AWS/1Password/helper boundaries and
real OpenSSL issuance/validation. They do not change real AWS or 1Password data.
Real macOS AWS/1Password acceptance, actual credential acquisition, and external
organization isolation remain operator acceptance work; see the explicit
[acceptance record](./testing.md#aws-acceptance-record-2026-10-23).

Implementation follows AWS's [trust model](https://docs.aws.amazon.com/rolesanywhere/latest/userguide/trust-model.html),
[CreateTrustAnchor API](https://docs.aws.amazon.com/cli/latest/reference/rolesanywhere/create-trust-anchor.html),
[CreateProfile API](https://docs.aws.amazon.com/cli/latest/reference/rolesanywhere/create-profile.html),
and [credential helper](https://docs.aws.amazon.com/rolesanywhere/latest/userguide/credential-helper.html),
plus 1Password's [item creation](https://www.1password.dev/cli/item-create)
and [item editing reference](https://www.1password.dev/cli/reference/management-commands/item#item-edit)
(checked October 23, 2026). AWS account checks and resource trust restrictions
provide useful safeguards, not proof of external production isolation.
