# Provisioning

Run `./provision` from the repository root on macOS after creating and starting the VM. Lima owns the VM lifecycle; Provisioning never creates, starts, stops, or deletes a VM. See the [usage guide](./usage.md#operating-workflow) for lifecycle commands and targeting another instance.

## What a rebuild restores

Provisioning applies the Development Baseline: the software and non-secret configuration needed for development. It uses Ansible for system state and tools, then installs `dotfiles/home` as one opaque Managed Dotfiles collection with GNU Stow. Ansible does not manage each application's configuration separately.

The Development Baseline includes command-line development tools, pinned language runtimes, Docker, GitHub CLI, Salesforce CLI, Teamwork Graph CLI, Neovim, Claude Code, OpenCode, T3 Code, and the Managed Dotfiles. Applications may download plugins or create caches and private state when first run after a rebuild.

Each Provisioning run installs pnpm, OpenCode, and T3 Code from their npm `latest` tags, upgrading existing installations when newer releases are available.

Provisioning also reads the stable release version from Atlassian's [TWG installer](https://teamwork-graph.atlassian.com/cli/install), downloads the Linux ARM64 binary, and verifies it against the matching vendor SHA-256 manifest. It reads the installer's `DEFAULT_VERSION` selector without executing the installer. A changed selector format or missing release/checksum fails Provisioning rather than silently choosing another release. The binary lives at `~/.local/share/proteus/twg/twg`, linked through `~/.local/bin/twg` and `/usr/local/bin/twg` so interactive shells and background agents find the same CLI.

Each run updates TWG and installs its official skills for the universal `~/.agents/skills` layout, Claude Code, and OpenCode. Managed Dotfiles add the shared `proteus-atlassian` skill in those locations: basic Jira/Confluence commands are the default, and Rovo-credit-consuming enriched operations require an explicit user request. This guidance is not an OAuth permission restriction. Provisioning installs `dbus-user-session` for TWG's Linux refresh helper but leaves authentication and upkeep activation to `./enroll twg`. Reprovisioning preserves credentials and the existing upkeep schedule; it does not start login or run the interactive TWG installer.

Salesforce CLI runs through an `sf` launcher in the Managed Dotfiles, exposed through `/usr/local/bin/sf` so background services such as T3 can find it without shell startup files. The launcher runs the official standalone Linux ARM64 archive with its bundled Node runtime and `SF_USE_GENERIC_UNIX_KEYCHAIN=true`, so credentials use Salesforce CLI's file-based keychain rather than a desktop keyring that background services cannot unlock, and `SF_DISABLE_TELEMETRY=true`, so the guest sends no usage data.

Salesforce CLI uses the official stable Linux ARM64 archive rather than npm. Both
are supported by Salesforce; the archive includes Node and removes the npm-prefix
lifecycle dependency without an advantage from retaining npm. On each explicit
Provisioning run, Ansible resolves the current stable build manifest, verifies the
archive's SHA-256 digest, extracts and checks the new release before activating
it. A failed download, checksum, or runtime check leaves the prior active release
available. Old standalone releases remain inactive under Proteus's tool directory.

The Managed Dotfiles launcher invokes the bundled Node and `bin/run.js` directly,
bypassing the vendor shell entry point's user-client redirection and custom Node
selection. It does not prepend its runtime to PATH: project commands spawned by
plugins retain the caller's project Node selection. Salesforce CLI can start even
when that project Node is absent. The launcher forces `SF_AUTOUPDATE_DISABLE=true`
and `SF_DISABLE_AUTOUPDATE=true`, as well as the keychain and telemetry settings,
including when inherited values conflict. Explicit Provisioning owns updates.

Migration uninstalls obsolete `@salesforce/cli` global packages (including `sf`
and `sfdx` commands) only from direct mise Node installation prefixes, including
retained older versions, and removes the previous Proteus-owned `sf` and `node`
launcher links. It preserves Node installations, unrelated packages, project-local
or custom prefixes, `.sf`, `.sfdx`, enrolled credentials, plugins, and user state.
Provisioning never performs Salesforce Credential Enrollment; the configured login
URL, `devhub` alias, and default Dev Hub workflow remain unchanged.

Vendor references: [Salesforce CLI installation and archive manifests](https://developer.salesforce.com/docs/platform/sfdx-setup/guide/sfdx-setup-install-cli.html)
and [disabling automatic updates](https://developer.salesforce.com/docs/platform/sfdx-setup/guide/sfdx-setup-disable-autoupdate.html).


Claude Code uses Anthropic's official standalone Linux ARM64 executable, independently of
mise Node installations and npm prefixes. Each explicit Provisioning reads the current
`latest` release and its `manifest.json` from
`https://downloads.claude.ai/claude-code-releases`, verifies the executable's SHA-256
against the manifest, and checks `--version` before replacing the command links.
The executable lives in `~/.local/share/proteus/claude/<version>/claude`;
`~/.local/bin/claude` and `/usr/local/bin/claude` select the same executable for
interactive shells, Credential Enrollment, and background services. It does not
resolve project Node or rewrite the child-command environment.

Migration uninstalls only `@anthropic-ai/claude-code` from retained mise Node
prefixes (including earlier Development Baselines), using each prefix's own npm
and Node. It replaces the obsolete command link without removing `~/.claude/`,
`~/.claude.json`, settings, history, credentials, or other npm packages. An npm
installation may already contain a native executable; this migration removes its
installation lifecycle coupling to Node rather than claiming it needs Node to run.
Installations outside the Provisioning-owned mise prefixes are left to the user.
Old standalone version directories are retained so a running executable is not
removed; they are versions of the same installation method.

Provisioning owns Claude Code updates. Managed settings set
`env.DISABLE_AUTOUPDATER=1`, disabling independent background updates for all
projects. Manual `claude update`/`claude install` remain vendor-supported overrides
and can introduce a competing native installation; use `./provision` for updates
and avoid those commands on Proteus. The distribution layout and update control
follow Anthropic's [installation and update documentation](https://code.claude.com/docs/en/setup)
and [official installer](https://claude.ai/install.sh). The checksum is obtained
via HTTPS from the vendor manifest, as in the installer; these tasks do not verify
the manifest's detached GPG signature.

Provisioning also registers the official Claude Code plugin marketplace and runs `claude plugin install mattpocock-skills@claude-plugins-official` as the guest user. The skills are installed at user scope for all projects. Installing this public plugin does not require Claude Code sign-in; run `./enroll claude` when you start using Claude Code.

Provisioning installs `/etc/claude-code/managed-settings.json`, which disables independent background updates, Claude Code's commit `Co-Authored-By` trailer and pull request footer. Managed settings take precedence over user and project settings, so attribution cannot be re-enabled per project; edit the Provisioning task to change it.

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
