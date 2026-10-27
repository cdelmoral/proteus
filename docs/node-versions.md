# Node versions and Proteus tools

Proteus uses mise as its only Node version manager. Provisioning retains pinned
mise 2026.9.1 and default Node 24.20.0. Outside configured projects, `node` uses
that default. In an interactive guest shell, entering a repository with `.nvmrc`,
`.node-version`, or `mise.toml` makes subsequent commands use its installed Node.
Switch directories normally; do not use `mise use --global` to switch projects.
Mise owns declaration resolution and precedence; Proteus does not parse these
files or rewrite project requirements.

For example, in a repository containing `.nvmrc`:

```bash
cd my-project
mise install node    # explicitly install the declared Node version
node --version
pnpm run build
pnpm test
```

For a new repository, `mise use --pin node@22.14.0` explicitly installs and records
that selection in `mise.toml`. Review a repository's `mise.toml` before running
`mise trust` if mise asks for trust; project configuration can execute code.
Use `mise install node@22.14.0` to install a specific version without recording a
new selection. Humans and agents may perform these explicit installations.

Normal selection and execution do not download runtimes. If the requested Node
is absent, `node` fails with mise's missing-version and installation guidance
instead of using the default or a system Node. Run `mise install node` from the
repository, then retry. Network access is needed for versions not yet installed.
The Managed Dotfiles configure mise's own shims for interactive execution, so
selection also works when changing directories within a shell command. pnpm and
its package scripts use the selected Node; this does not establish a new policy
for project package-manager versions.

Repeated Provisioning restores the pinned global default and retains additional
installed versions. A rebuild restores only the Development Baseline. Clone your
repositories again and explicitly install their required Node versions from their
declarations; project runtimes are workspace state, not a backup maintained by
Proteus.

Proteus tool installations have a separate update lifecycle from project Node.
Explicit Provisioning owns tool updates. T3 service runtime updates and restarts
remain explicit T3 operations, separate from updating the CLI.

## Background commands and existing T3 services

Provisioning exposes `node`, `npm`, and `npx` through mise's shims in both
`~/.local/bin` and `/usr/local/bin`, and exposes the existing pnpm entrypoint in
`/usr/local/bin`. A background process with the usual system PATH therefore
selects Node from its working directory without reading `.bashrc`. The shims
resolve again on each invocation, including after `cd` in a noninteractive shell.
pnpm remains installed once and its Node interpreter uses project selection.

An enrolled T3 service keeps its running executable, runtime, environment and
credentials. Provisioning does not restart, upgrade, replace, or reenroll it.
Project command environments are configured at the provider shell boundary:

- Claude's managed `CLAUDE_ENV_FILE` sources the Managed Dotfiles
  `project-env.sh` before each Bash command, after shell state restoration.
- OpenCode's managed launcher supplies `BASH_ENV` and an extra configuration
  selecting Bash. This configuration merges with normal user configuration;
  it does not replace credentials or user settings. An explicit caller
  `OPENCODE_CONFIG` is retained. A global `shell.env` plugin also prepends the
  managed entrypoints for OpenCode's legacy shell implementation. OpenCode V2
  currently lacks that plugin hook, so its configured Bash startup is required.
- Codex's system configuration supplies `shell_environment_policy.set` for
  command PATH and `BASH_ENV`, including when T3 uses a shadow `CODEX_HOME`.
  This PATH includes managed entrypoints and standard system directories, not
  the provider's private runtime directory. Add custom command search locations
  through Codex configuration if needed. Existing unrelated system settings are
  retained; a conflicting existing `[shell_environment_policy.set]` table fails
  validation without overwriting it and needs an explicit configuration merge.
- Login shells source the same managed environment from `/etc/profile.d` so
  shell startup and newly captured snapshots use shims rather than concrete Node
  prefixes. The provider's interpreter is never selected through this script.

These mechanisms select mise shims, not baseline Node. Direct `node`, `npm`,
`npx`, `pnpm run build`, and `pnpm test` therefore resolve from their command's
working directory, including after `cd`. Ordinary execution still never installs
Node. No per-command helper prefix should be necessary in a provider session
that has loaded this configuration.

Provisioning cannot rewrite the in-memory environment, cached shell snapshot or
loaded plugins of an already running provider. T3 provider-instance environment
settings merge into new provider launches; they are not a command-shell hook or
a live mutation API. Current T3 supports custom provider binaries and environment
variables, but has no universal agent-command-shell setting. Merely changing
service PATH on disk cannot repair already captured state. This is a residual
limit for preexisting sessions, not a reason to restart the enrolled service.
New provider sessions can load the boundary configuration while that service
continues running on its original runtime. Do not restart, upgrade or reenroll
T3 to apply this change automatically.

User/project configuration or T3 launch overrides can supersede Codex defaults
or OpenCode's shell choice. A direct vendor-binary override can bypass the
managed OpenCode launcher. Explicit absolute Node paths remain explicit runtime
choices. A preexisting Codex snapshot or provider environment that restores a
private Node PATH must be checked through actual T3 execution. Until verified,
use the absolute recovery entrypoint from the repository directory:

```bash
/usr/local/bin/proteus-project-exec pnpm run build
/usr/local/bin/proteus-project-exec pnpm test
/usr/local/bin/proteus-project-exec "$HOME/.local/bin/mise" install node
```

The helper is a recovery path; its success alone is not proof of automatic T3
selection. Do not wrap the service or every child in a baseline-Node PATH.

## Real T3 acceptance

`make lima-acceptance` checks the disposable guest's real artifacts, interactive
shells and transient systemd commands. Its synthetic parent/helper tests are
component coverage; they do **not** prove the actual T3 agent boundary.

Real T3 coverage requires an existing, explicitly authorized Lima guest with
Provisioning applied and Claude, OpenCode and Codex already available through
T3. From macOS, prepare temporary projects without enrollment or service changes:

```bash
./tests/lima_acceptance.sh --t3-node-prepare proteus
```

This explicitly installs Node 22.14.0 and 20.19.0 without changing the global
default. It prints a workspace and one probe command for each provider. Ask an
agent in each corresponding T3 provider to execute its printed command through
its normal shell tool, with no helper, PATH override or manual sourcing. Run
providers sequentially; each probe checks concurrent Node execution internally.
Keep the actual T3 command activity as provenance alongside the generated JSON.
The probe records inherited PATH and process ancestry (names and executable
paths, not command arguments), and checks all three declarations, default
selection, directory switching, pnpm builds/tests, failure propagation, missing
runtime failure and unchanged global selection. It fails if the managed helper
is missing or inherited private Node wins. Do not simulate these result files.

Then validate all three results using the workspace printed by preparation:

```bash
./tests/lima_acceptance.sh --t3-node-verify proteus /tmp/proteus-t3-node.EXAMPLE
```

Missing evidence fails validation. A JSON result alone does not authenticate its
execution source: inspect the saved T3 activity. Retain results before explicitly
removing the temporary workspace. No credentials are enrolled and no service
is installed, restarted or upgraded by either mode. This acceptance has **not**
been run for these review fixes: the implementation host is Linux ARM64, without
the authorized macOS/Lima/Connect environment. Provider-specific behavior and
preservation of a real enrolled service remain unverified until that run.

Boundary references checked on 2026-10-27:
[Claude command environment](https://code.claude.com/docs/en/env-vars),
[Codex shell environment policy](https://developers.openai.com/codex/config-reference/),
[Codex configuration precedence](https://learn.chatgpt.com/docs/config-file/config-basic),
[OpenCode shell environment plugins](https://opencode.ai/docs/plugins/), and
[OpenCode configuration merging](https://opencode.ai/docs/config/).
T3's [provider setup](https://github.com/pingdotgg/t3code/blob/36d4d711b79c73eb33131944f73ea4a8c6156484/docs/user/install.md#providers),
[instance environment merge](https://github.com/pingdotgg/t3code/blob/36d4d711b79c73eb33131944f73ea4a8c6156484/packages/provider-core/src/server/instanceEnvironment.ts),
and [OpenCode process launch](https://github.com/pingdotgg/t3code/blob/36d4d711b79c73eb33131944f73ea4a8c6156484/packages/provider-opencode/src/server/OpenCodeRuntime.ts)
show the provider launch boundary. OpenCode v1.19.4's
[legacy shell hook](https://github.com/anomalyco/opencode/blob/v1.19.4/packages/opencode/src/tool/shell.ts)
and [V2 shell implementation](https://github.com/anomalyco/opencode/blob/v1.19.4/packages/core/src/tool/bash.ts)
show the version-specific hook limitation. Installed versions can differ; real
acceptance against the enrolled environment is still required.

Mise references: [Node declarations](https://mise.jdx.dev/lang/node.html),
[shim selection](https://mise.jdx.dev/dev-tools/shims.html), and
[settings for pinned mise 2026.9.1](https://github.com/jdx/mise/blob/v2026.9.1/settings.toml)
(`auto_install`, `not_found_auto_install`, `not_found_system_fallback`, and
`idiomatic_version_file_enable_tools`).

OpenCode is installed from the official Linux ARM64 binary, independently of
mise's Node installations. It launches even when a project's requested Node is
missing. Its launcher disables independent auto-updates without changing PATH,
so project subprocesses retain the caller's Node selection. Run `./provision`
to update OpenCode; see [Provisioning](./provisioning.md) for release compatibility
and rebuild instructions.

Salesforce CLI is installed from its official Linux ARM64 standalone archive,
with its own bundled Node runtime. The managed `sf` command works through the
system PATH without shell initialization or an installed project Node. It keeps
the caller's PATH for project subprocesses. Provisioning selects current stable
releases and disables independent automatic updates, preserving Salesforce state.
Older npm baselines require a fresh VM under the
[release policy](./provisioning.md#release-compatibility-and-rebuilds).
