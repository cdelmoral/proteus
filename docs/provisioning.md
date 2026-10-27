# Provisioning

Run `./provision` from the repository root on macOS after creating and starting the VM. Lima owns the VM lifecycle; Provisioning never creates, starts, stops, or deletes a VM. See the [usage guide](./usage.md#operating-workflow) for lifecycle commands and targeting another instance.

## What a rebuild restores

Provisioning applies the Development Baseline: the software and non-secret configuration needed for development. It uses Ansible for system state and tools, then installs `dotfiles/home` as one opaque Managed Dotfiles collection with GNU Stow. Ansible does not manage each application's configuration separately.

The Development Baseline includes command-line development tools, pinned language runtimes, Docker, GitHub CLI, Salesforce CLI, Teamwork Graph CLI, Neovim, Claude Code, OpenCode, T3 Code, and the Managed Dotfiles. Applications may download plugins or create caches and private state when first run after a rebuild.

Each Provisioning run installs pnpm, Claude Code, T3 Code, and Salesforce CLI (`@salesforce/cli`) from their npm `latest` tags, upgrading existing installations when newer releases are available.

OpenCode uses the official `opencode-linux-arm64.tar.gz` glibc binary from the
[current GitHub release](https://github.com/anomalyco/opencode/releases/latest),
verified against the asset's SHA-256 digest returned by GitHub. Every explicit
Provisioning run resolves the current release, verifies and launches the candidate,
then installs it in `~/.local/share/proteus/opencode/opencode`. Failed downloads,
digest verification, or candidate launches leave the previous installation intact.
The Managed Dotfiles `opencode` launcher is exposed through `~/.local/bin` and
`/usr/local/bin` for interactive shells and background agents. It sets the supported
[`OPENCODE_DISABLE_AUTOUPDATE`](https://opencode.ai/docs/cli/#environment-variables)
flag and preserves PATH, arguments, and exit status. OpenCode needs no development
Node runtime; its project subprocesses inherit the project's environment.

Migration removes only `opencode-ai` from the Provisioning-owned baseline Node
prefix and command symlinks targeting that old installation. It does not invoke
`opencode uninstall`, remove other Node installations, or touch OpenCode
configuration, credentials, skills, sessions, caches, or history. An unrelated
user command at the Managed Dotfiles destination is preserved and reported as a
Stow conflict; resolve that conflict before retrying. Keep updates owned by
`./provision`; avoid separate npm installs or `opencode upgrade`, which would
introduce a competing installation path. The installation uses the same official
Linux archive as the [vendor installer](https://opencode.ai/install), without
executing that installer or changing shell startup files.

Provisioning also reads the stable release version from Atlassian's [TWG installer](https://teamwork-graph.atlassian.com/cli/install), downloads the Linux ARM64 binary, and verifies it against the matching vendor SHA-256 manifest. It reads the installer's `DEFAULT_VERSION` selector without executing the installer. A changed selector format or missing release/checksum fails Provisioning rather than silently choosing another release. The binary lives at `~/.local/share/proteus/twg/twg`, linked through `~/.local/bin/twg` and `/usr/local/bin/twg` so interactive shells and background agents find the same CLI.

Each run updates TWG and installs its official skills for the universal `~/.agents/skills` layout, Claude Code, and OpenCode. Managed Dotfiles add the shared `proteus-atlassian` skill in those locations: basic Jira/Confluence commands are the default, and Rovo-credit-consuming enriched operations require an explicit user request. This guidance is not an OAuth permission restriction. Provisioning installs `dbus-user-session` for TWG's Linux refresh helper but leaves authentication and upkeep activation to `./enroll twg`. Reprovisioning preserves credentials and the existing upkeep schedule; it does not start login or run the interactive TWG installer.

Salesforce CLI runs through an `sf` launcher in the Managed Dotfiles, exposed through `/usr/local/bin/sf` so background services such as T3 can find it without shell startup files. The launcher runs the npm-installed CLI on the managed Node runtime with `SF_USE_GENERIC_UNIX_KEYCHAIN=true`, so credentials use Salesforce CLI's file-based keychain rather than a desktop keyring that background services cannot unlock, and `SF_DISABLE_TELEMETRY=true`, so the guest sends no usage data.

Provisioning also registers the official Claude Code plugin marketplace and runs `claude plugin install mattpocock-skills@claude-plugins-official` as the guest user. The skills are installed at user scope for all projects. Installing this public plugin does not require Claude Code sign-in; run `./enroll claude` when you start using Claude Code.

Provisioning installs `/etc/claude-code/managed-settings.json`, which disables Claude Code's commit `Co-Authored-By` trailer and pull request footer. Managed settings take precedence over user and project settings, so attribution cannot be re-enabled per project; edit the Provisioning task to change it.

A rebuild does not restore VM-Local Credentials, Host-Injected Credentials, project repositories, uncommitted work, command history, caches, application state, or workspace state. Back up or publish work that must survive before deleting Proteus. Credential Enrollment and repository cloning happen again in the new guest.

T3 Code is installed as a command only. Provisioning does not start it, run a background service, expose a port, pair a client, configure T3 Connect, or choose another connection method. Run `./enroll t3` explicitly to authorize T3 Connect and install its persistent guest service. The service uses a separate pinned runtime; subsequent Provisioning upgrades the npm CLI without updating or restarting that service. Service upgrades remain explicit T3 operations.

See [rebuilding Proteus](./usage.md#rebuild-proteus) for the rebuild procedure and [Credential Enrollment](./credentials.md) for authentication after Provisioning.

## AWS tools

Provisioning installs AWS CLI v2 **2.38.5** for Linux ARM64 and Roles Anywhere helper **1.8.5**, with pinned SHA-256 digests in `provisioning/group_vars/all.yml`. Both commands are exposed in `/usr/local/bin` for noninteractive processes. Unsupported architectures fail before AWS installation. No AWS credentials, references, or `~/.aws` settings are read or written by these tasks; explicit [AWS Credential Enrollment](./aws-enrollment.md) follows Provisioning.

The CLI archive digest was computed after verifying its detached signature from `awscli.amazonaws.com` using the AWS CLI Team key fingerprint `FB5D B77F D5C1 18B8 0511 ADA8 A631 0ACC 4672 475C`, obtained from AWS's [official installation instructions](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html). Pinned archive: `https://awscli.amazonaws.com/awscli-exe-linux-aarch64-2.38.5.zip` (signature at the same URL plus `.sig`). The helper digest is published in AWS's [credential-helper download table](https://docs.aws.amazon.com/rolesanywhere/latest/userguide/credential-helper.html). When upgrading pins, verify the CLI signature and the helper's release checksum against those primary sources before recording new digests.

After a rebuild, retain/restore the non-secret host configuration and explicitly
reenroll the persistent workload pair; there is no need to recreate AWS trust.
If its certificate expired, use [host replacement](./aws-setup.md#annual-replacement-and-expiration-recovery)
first. Updating the baseline of an existing guest preserves active enrollment.
