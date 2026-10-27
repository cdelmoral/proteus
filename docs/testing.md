# Testing Proteus

Run these commands from the repository root.

## Automated checks

Run `make static test` to validate Provisioning and the VM Definition and exercise enrollment with simulated CLI tools. The enrollment tests use separate host and guest homes and a real terminal without contacting 1Password, Claude, T3 Connect, Salesforce, or Atlassian. When running the tests from T3 with `T3CODE_HOME` set, use `env -u T3CODE_HOME make static test` so its location does not override the simulated guest home.

Teamwork Graph tests run the real enrollment helper and simulate TWG and lingering commands. They cover guest-local authorization, preserving healthy credentials, minimal native verification, upkeep failures and retries, custom instances, and terminal/VM prerequisites. Unexpected product probes or service-health commands fail the simulated CLI.

Salesforce tests run the real launcher, enrollment helper, and URL-capture script in the guest home and simulate only the standalone Salesforce CLI, which opens its authorization URL through `BROWSER` as Salesforce CLI does. They cover login, browser-launch, and verification failures, repeat enrollment, and VM and terminal checks. Configuration tests drive `./configure` to save, keep, and reject Salesforce login URLs while preserving the GitHub references, and confirm the saved URL or the standard default reaches Salesforce CLI. Salesforce CLI tests run the managed `sf` launcher from the system PATH without shell startup and simulate only the archive runtime and CLI, verifying keychain, telemetry and updater settings, argument forwarding, failure propagation, and unchanged child PATH across installed and missing project runtimes. Salesforce Provisioning tests run real Ansible tasks against a local manifest and archive, including digest/runtime failures, repeat runs, upgrades, obsolete npm cleanup, and preservation of dummy user state.

T3 tests simulate systemd, lingering, and provider-independent Connect setup, including partial failures, retries, and existing-server protection. They verify completion from saved Connect configuration and systemd persistence, including links saved after startup and healthy services without private runtime metadata.

GitHub credential tests require Git, GitHub CLI, and OpenSSH. They exercise real credential lookup with dummy tokens and real signing with temporary keys, without network access. They cover background Git and `gh` commands, commit signing without a terminal or SSH agent, identity preservation, reprovisioning, credential rotation, invalid or encrypted keys, rejected tokens, missing references, and failed secret reads. Configure tests cover reference examples, preserving both defaults, upgrading token-only configuration, and interrupted input.

The focused Node tests execute pinned mise against temporary homes and isolated fixture executables, without downloading Node or touching the user's mise configuration. Run them with `PROTEUS_TEST_MISE=/absolute/path/to/mise-2026.9.1 python3 -m unittest discover -s tests -p test_node_selection.py`. Without this variable they skip; these fixtures verify mise selection and missing-version behavior, while real Node/pnpm integration belongs to Lima acceptance.

OpenCode tests execute the real Ansible installation tasks against a local HTTP
release feed and fixture archives. They verify digest and platform rejection,
failed candidates preserving the old installation, migration, repeat runs and
updates, unrelated command preservation, and untouched user state. A real launcher
test verifies argument forwarding, failure propagation, the auto-update flag, and
child command resolution through an unchanged project PATH. The vendor executable
is simulated in these focused tests. They do not prove vendor ARM64 compatibility
or real T3 execution. The Lima checks below exercise the real vendor distribution;
a provider-authenticated OpenCode task spawning a project command through T3 is
still part of spec #50's Node-selection acceptance.

OpenCode #54 implementation validation ran on Linux. Real macOS/Lima acceptance
remains **unrun**; do not interpret local fixture results as guest evidence.

## Manual acceptance

Run the real macOS-to-Lima acceptance check manually:

```bash
make lima-acceptance
```

The check validates the production VM Definition, creates and starts a uniquely named `proteus-acceptance-*` VM, and runs production Provisioning twice. Claude assertions are isolated in `tests/claude_guest_acceptance.py`: the fresh run checks actual ARM64 artifact compatibility, interactive and system-PATH command availability, public marketplace/skills installation, managed attribution/update policy, and unauthenticated status with project Node blocked. It then seeds the obsolete vendor npm installation and dummy credential, configuration, and history state.

Node assertions in `tests/lima_node_selection.py` use temporary repositories to exercise `.nvmrc`, `.node-version`, and `mise.toml`, interactive directory switching and default selection, explicit installation, missing-version failures without download, and pnpm build/test scripts with observed runtimes and failure propagation. They deliberately change the global default before the second Provisioning run.

The Node runner also launches real transient systemd user services with an empty
environment plus HOME and a minimal system PATH, without shell initialization.
It checks node/npm across all declarations, concurrently running projects on
different versions, missing node/npm/pnpm failure, OpenCode availability before
recovery, and explicit `mise install node` from that background environment.
A real baseline Node parent launches project pnpm build/test and npm commands
through `proteus-project-exec` with a deliberately inherited baseline-first PATH;
the parent retains its version while children use project Node. Argument and
failure propagation are checked. Both Provisioning passes exercise these paths.
The disposable guest must have a functioning systemd user manager; failure to
launch a transient service fails acceptance rather than substituting a fixture.
This requires no T3 enrollment and does not touch an existing T3 service.

Claude, Salesforce, and OpenCode migration fixtures are seeded before Node assertions change the global default. The shared repeated run must migrate their obsolete npm installations and preserve each tool's user state, restore the pinned Node default, and retain usable additional project versions. No real Credential Enrollment is performed. Setup, assertions, Provisioning, and cleanup failures fail the command. This checks observable behavior rather than exact convergence of all Provisioning tasks.

Focused Claude tests execute the actual Ansible tasks with a local HTTP vendor fixture and real npm migration across retained Node prefixes. They exercise upgrades, checksum/selector failures, user-state preservation, and child environment preservation. Enrollment subprocess tests confirm that login/status no longer require mise. These fixtures do not prove Linux ARM64 vendor compatibility or real authentication.

Claude guest acceptance evidence: **unrun** on the Linux implementation host. Run `make lima-acceptance` on macOS and record the date, guest architecture, Claude version, and fresh/repeated outcomes before claiming guest acceptance. Real `./enroll claude` and subsequent authenticated status also remain manual, unrun checks requiring the owner's authorization; they are not part of the automated acceptance flow. Node guest acceptance is also **unrun** on this host.

For #52, real authenticated T3 acceptance remains **unrun**. In the existing
enrolled service, record the service PID/runtime and agent PATH before and after
Provisioning without restarting it. From an agent run the two project versions
concurrently, pnpm build/test, a missing-version failure followed by explicit
installation, and a tool-parent/project-child command. Use the absolute
`proteus-project-exec` entrypoint if the service has a private runtime first on
PATH, as described in [Node operations](./node-versions.md). Record whether direct
commands or the explicit entrypoint were used, actual versions, exit statuses,
and unchanged service PID/runtime. Transient systemd services prove guest
background behavior when run; they do not prove T3's provider subprocess
environment. Local mise tests use fixture Node executables and prove neither.

#52 local validation (2026-10-27, Linux ARM64): static checks passed; the bounded
suite completed 132 tests with one npm-prerequisite skip, and that migration test
passed separately with the existing npm runtime on PATH. All runs unset
`T3CODE_HOME`. Six Node tests passed using pinned mise and isolated fixture
executables. These results do not establish Lima or authenticated T3 acceptance.

OpenCode migration is seeded before Node assertions change the global default.
After the shared second Provisioning run, `tests/lima_opencode.sh` verifies the
installed vendor binary is ARM64 ELF, the obsolete baseline npm installation is
gone, user configuration/credentials/skills/state survive byte for byte, and
interactive and minimal background environments find the same OpenCode launcher.
OpenCode must launch from a temporary project requesting an uninstalled Node
version without installing it; a failing Node executable on the background PATH
detects accidental runtime coupling.

The check refuses to adopt an existing instance and deletes the VM it created after success or failure. It disables development-port forwarding for that VM, so the normal `proteus` instance may remain running.

To verify GitHub Credential Enrollment manually on macOS, configure both 1Password references and register the signing public key with GitHub once. Create and start a fresh VM, run `./provision`, run `./enroll github`, and enter a new guest shell. Confirm `gh auth status` and one HTTPS Git operation succeed. Repeat the Git operation and `gh api user --silent` through non-interactive guest commands with `GH_TOKEN` and `GITHUB_TOKEN` unset, and again after Provisioning. Confirm both a private project clone and a GitHub CLI command through T3's background service succeed. Make a commit with the existing Git identity through T3 and confirm GitHub shows its signature as verified. Repeat enrollment and Provisioning and confirm signing still works. Do not print or inspect the token or private key.

Run `./enroll claude` from an interactive terminal, complete browser authorization, and confirm `claude auth status` succeeds inside the guest. Stop and start the VM to confirm the login persists. Repeat enrollment after a rebuild.

For Teamwork Graph, run `./enroll twg`, authorize your personal account through the printed verification URL, and select the default site. Confirm completion, then repeat enrollment and confirm no new browser login is requested. Completion intentionally uses only `twg doctor --basic` and successful upkeep activation. Reading/searching or testing Jira/Confluence writes is a separate optional acceptance exercise using a test issue/page you select. Before deleting the VM, follow the logout/revocation steps in [Teamwork Graph Enrollment](./credentials.md#teamwork-graph).

For T3, run `./enroll t3` on a fresh provisioned VM from an interactive macOS terminal. Accept relay-client and service installation, approve the browser code, and confirm local verification completes. Sign in to the same T3 Connect account from another device and connect to the environment. Close the guest shell, then stop/start the VM; confirm the service and remote access return without running enrollment again. Authenticate a provider separately to run agent work.

Repeat T3 enrollment and confirm it leaves the running service untouched. Verify that a service on a different version from the npm CLI still passes when healthy. Decline or interrupt setup, confirm incomplete setup is reported, and retry using the saved authorization. Start a foreground server and confirm enrollment refuses takeover. For a running service started before Connect was enabled, confirm enrollment saves authorization and environment linking without restarting it or rejecting the new link's timestamp. Verify remote access from another device; if activation needs a restart, perform it explicitly when ready. After deleting the VM, deregister its old cloud environment and enroll the replacement afresh.

The existing `make lima-acceptance` flow also verifies Salesforce's real Linux
ARM64 archive, system PATH and user-systemd background availability, launches with
two installed Node runtimes and an absent project runtime, interactive execution,
CLI failures, repeat Provisioning and obsolete npm migration. It installs the
additional Node explicitly and seeds only dummy Salesforce state; it never logs
in. Fixture tests do not establish real guest or macOS/Lima compatibility. The
manual Salesforce Credential Enrollment checks below still require a human.

For Salesforce, run `./configure` with your org's login URL, then run `./enroll salesforce` on a fresh provisioned VM from an interactive macOS terminal. Open the printed URL in the macOS browser, log in as the Dev Hub User, approve access, and confirm enrollment reports success. Inside the guest, create a scratch org, run a command against it, and open it with `sf org open --url-only`. Run `sf org list` through T3's background service. Stop and start the VM and confirm the authorization persists, then re-enroll. After a rebuild, follow the scratch org deletion and OAuth revocation steps for the old VM and enroll the replacement.

See [Credential Enrollment](./credentials.md) for authentication details and [VM details](../vm/README.md) for the isolation boundary, Docker privilege, and port forwarding.

## AWS acceptance

AWS tests execute the public configuration and enrollment commands, real guest helper, and real OpenSSL against isolated homes; only installation paths and external Lima, 1Password, helper, and AWS command boundaries are simulated. They check complete configuration, opt-out, retained settings, secret resolution before transfer, prerequisites/custom instances, private files, certificate/key validation, failed candidates preserving active generations, wrong identities, ambient interference, and default-profile use without an interactive shell. AWS Provisioning tests run the real installation tasks against local fixture downloads and a simulated vendor installer, checking checksum rejection, architecture checks, executable availability, repeat installation, and preserved enrollment files. Simulated AWS calls do not prove real AWS trust or production isolation.

On a real macOS-to-Lima installation with externally verified development-account isolation, configure and enroll the workload pair from 1Password. Confirm `aws sts get-caller-identity` reports the intended account and role, then run a permitted AWS read from an agent through T3 without AWS access-key environment variables. Repeat after temporary session expiry to verify fresh acquisition, after VM stop/start, after Provisioning, and after rebuilding and explicit reenrollment. Replace the certificate/key pair and reenroll; try an invalid replacement and confirm the previous usable identity remains active. Exercise expiration recovery and review revocation with the external account administrator using [the AWS guide](./aws-enrollment.md). These manual checks require real trust resources and were not performed by the automated suite.

### AWS acceptance record (2026-10-23)

Implementation environment: Linux, with isolated host/guest homes. No real
macOS/Lima installation or authorized real AWS/1Password mutation is available.
**Real acceptance remains unrun.** Automated results below are simulated service
results with real local OpenSSL certificates, not external acceptance evidence.

Local validation passed: `PATH=/tmp/proteus-spec41-tools/bin:/tmp/proteus-spec41-lima/bin:$PATH env -u T3CODE_HOME make static test`
completed static checks and **117 tests, zero failures, zero skips**. CI uses the
same Make targets, with OpenSSL installed explicitly; `make static` parses the
Python entrypoints/modules/tests and `make test` discovers the lifecycle suite.

`make test` discovers `test_aws_lifecycle.py` alongside the setup, configuration,
enrollment and Provisioning suites. The lifecycle suite executes the public
`aws-setup`, `configure` and `enroll aws` commands and real guest helper. It feeds
setup's emitted values through configuration prompts, resolves the simulated
persistent workload item, replaces certificates, checks failed issuance/item
updates/verification/reenrollment preserve prior state, recovers from an expired
CA-signed workload certificate, and reenrolls into an empty guest enrollment home
with installed tools. This fresh-home case simulates credential recovery after a
rebuild; it does not boot or provision a real VM. Helper/AWS requests are simulated
and do not demonstrate real session refresh or real T3 process behavior.

| Real acceptance case | Status | Reason / evidence to record on macOS |
| --- | --- | --- |
| Initial setup and 1Password-backed enrollment | Unrun | Needs authorized real vault/cloud writes and macOS; record resource IDs, certificate expiry, command outcomes without secrets. |
| Exact AWS account and assumed role | Unrun | Needs real Roles Anywhere trust; record STS account/role ARN. |
| AWS read from an agent through persistent T3 | Unrun | Needs running macOS/Lima/T3 deployment; record a permitted read without login-shell initialization or exported access keys. |
| Fresh acquisition after temporary session expiry | Unrun | Needs real issued sessions and elapsed expiry; record session expiry and successful later AWS read with the same valid workload certificate. |
| VM stop/start | Unrun | No real macOS Lima VM; record identity and agent read before/after stop/start. |
| Provisioning preserves enrollment | Unrun | Local task fixture only; record identity before/after real `./provision`. |
| Certificate replacement and failed replacement preservation | Unrun | Local lifecycle fixture only; record changed serial/expiry, unchanged CA/resource ARNs, successful reenrollment, and rejected candidate leaving the prior guest generation active. |
| Workload expiration recovery | Unrun | Local expired-certificate fixture only; use a controlled test identity, original CA and host administrative access; record renewal and reenrollment outcomes. |
| Rebuild and explicit reenrollment | Unrun | Empty-home fixture only; record restored tools, no access before enrollment, same account/role and successful agent read afterward without recreating trust. |
| Emergency revocation and compromised-material recovery | Unrun | Requires external administrator and authorized controlled exercise; verify issuance stops, separately address issued sessions, revoke compromised certificates/replace compromised CA trust before reenablement. |
| External production/cross-account isolation | Not established | Requires independent organization/trust review; account identity and simulated tests cannot prove it. |

Run the real cases only with an approved isolated development identity. Keep keys,
SSO tokens, temporary credentials and vault contents out of the acceptance record.
Use the [setup, replacement and rebuild guide](./aws-setup.md) and
[AWS Credential Enrollment guide](./aws-enrollment.md) as the operating steps.
Record actual outcomes and dates here when acceptance is performed; do not mark
these rows passed from automated fixtures. `make lima-acceptance` checks baseline
Provisioning and project Node selection; it does not run this AWS matrix.
