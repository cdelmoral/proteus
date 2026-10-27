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

Mise references: [Node declarations](https://mise.jdx.dev/lang/node.html),
[shim selection](https://mise.jdx.dev/dev-tools/shims.html), and
[settings for pinned mise 2026.9.1](https://github.com/jdx/mise/blob/v2026.9.1/settings.toml)
(`auto_install`, `not_found_auto_install`, `not_found_system_fallback`, and
`idiomatic_version_file_enable_tools`).
