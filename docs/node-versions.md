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
An existing service may have captured a PATH with a private Node directory before
`/usr/local/bin`, or omit `/usr/local/bin` entirely. Updating files cannot change
that inherited PATH. From an agent in such a service, run project commands with
the absolute managed entrypoint, starting in the repository directory:

```bash
/usr/local/bin/proteus-project-exec node --version
/usr/local/bin/proteus-project-exec pnpm run build
/usr/local/bin/proteus-project-exec pnpm test
/usr/local/bin/proteus-project-exec sh -c 'node --version; cd ../other-project; node --version'
```

`proteus-project-exec` prepends the managed project entrypoints and mise shims to
the child's PATH and preserves arguments and exit status. It does not select a
baseline Node for the child or change the parent tool's interpreter. Use it at
the project-command boundary when a tool supplies its own runtime PATH. Absolute
runtime paths supplied by a project or tool remain explicit runtime choices.

To recover an absent runtime through the same background environment:

```bash
/usr/local/bin/proteus-project-exec "$HOME/.local/bin/mise" install node
/usr/local/bin/proteus-project-exec pnpm test
```

Review and trust `mise.toml` first if required. Ordinary execution does not
install a version or fall back. The tool preparing the project can remain on its
own runtime while installation runs. No Credential Enrollment is needed.

For direct unprefixed commands in an older T3 service, inspect its effective PATH
and command resolution from an agent (`printf '%s\n' "$PATH"; command -v node`).
If its private runtime wins, keep using the explicit entrypoint. A permanent
service PATH migration requires a separately planned, explicit T3 service
operation during a suitable interruption window: preserve its pinned executable
and credentials, arrange for `/usr/local/bin` before concrete Node prefixes in
the child environment, and verify project commands after restart. CLI updates
and repeated enrollment do not authorize that migration. Do not wrap the T3
service in a blanket baseline-Node PATH; that would also override child projects.

Mise references: [Node declarations](https://mise.jdx.dev/lang/node.html),
[shim selection](https://mise.jdx.dev/dev-tools/shims.html), and
[settings for pinned mise 2026.9.1](https://github.com/jdx/mise/blob/v2026.9.1/settings.toml)
(`auto_install`, `not_found_auto_install`, `not_found_system_fallback`, and
`idiomatic_version_file_enable_tools`).

OpenCode is installed from the official Linux ARM64 binary, independently of
mise's Node installations. It launches even when a project's requested Node is
missing. Its launcher disables independent auto-updates without changing PATH,
so project subprocesses retain the caller's Node selection. Run `./provision`
to update OpenCode; see [Provisioning](./provisioning.md) for migration details.

Salesforce CLI is installed from its official Linux ARM64 standalone archive,
with its own bundled Node runtime. The managed `sf` command works through the
system PATH without shell initialization or an installed project Node. It keeps
the caller's PATH for project subprocesses. Provisioning selects current stable
releases and disables independent automatic updates; migration removes only the
previous managed npm installation and runtime links, preserving Salesforce state.
