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

Salesforce CLI is installed from its official Linux ARM64 standalone archive,
with its own bundled Node runtime. The managed `sf` command works through the
system PATH without shell initialization or an installed project Node. It keeps
the caller's PATH for project subprocesses. Provisioning selects current stable
releases and disables independent automatic updates; migration removes only the
previous managed npm installation and runtime links, preserving Salesforce state.
