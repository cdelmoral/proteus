# Node versions and Proteus tools

Proteus uses mise as its only Node version manager. Provisioning restores one
pinned default Node version; additional project versions belong to the guest's
workspace state and must be installed again after a rebuild.

Projects may declare Node in `.nvmrc`, `.node-version`, or `mise.toml`. Install
additional versions explicitly rather than changing the global default to switch
projects. Normal project command execution must not download a missing runtime.

Proteus tool installations have a separate update lifecycle from project Node.
Explicit Provisioning owns tool updates. T3 service runtime updates and restarts
remain explicit T3 operations, separate from updating the CLI.

OpenCode is installed from the official Linux ARM64 binary, independently of
mise's Node installations. It launches even when a project's requested Node is
missing. Its launcher disables independent auto-updates without changing PATH,
so project subprocesses retain the caller's Node selection. Run `./provision`
to update OpenCode; see [Provisioning](./provisioning.md) for migration details.
