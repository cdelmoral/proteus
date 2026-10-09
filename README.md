# Proteus

Proteus is one named, Rebuildable Dev VM for personal development on an Apple silicon Mac. Its Lima instance is named `proteus`. Normal work returns to the same VM; when it becomes broken or cluttered, replace it from the VM Definition and run Provisioning again.

Proteus is also a Credential-Isolated Dev VM. It does not mount host directories, import host SSH public keys, or forward the host SSH agent. The guest cannot access 1Password or ambient credentials stored on macOS. The trusted host may explicitly install a selected Host-Injected Credential, such as the GitHub token described below.

## What a rebuild restores

Provisioning applies the Development Baseline: the software and non-secret configuration needed for development. It uses Ansible for system state and tools, then installs `dotfiles/home` as one opaque Managed Dotfiles collection with GNU Stow. Ansible does not manage each application's configuration separately.

The Development Baseline includes command-line development tools, pinned language runtimes, Docker, GitHub CLI, Neovim, Claude Code, OpenCode, T3 Code, and the Managed Dotfiles. Applications may download plugins or create caches and private state when first run after a rebuild.

Each Provisioning run installs pnpm, Claude Code, OpenCode, and T3 Code from their npm `latest` tags, upgrading existing installations when newer releases are available.

Provisioning also registers the official Claude Code plugin marketplace and runs `claude plugin install mattpocock-skills@claude-plugins-official` as the guest user. The skills are installed at user scope for all projects. Installing this public plugin does not require Claude Code sign-in; authenticate inside the guest when you start using Claude Code.

A rebuild does not restore VM-Local Credentials, Host-Injected Credentials, project repositories, uncommitted work, command history, caches, application state, or workspace state. Back up or publish work that must survive before deleting Proteus. Credential Enrollment and repository cloning happen again in the new guest.

T3 Code is installed as a command only. Provisioning does not start it, run a background service, expose a port, pair a client, configure T3 Connect, or choose another connection method.

## Requirements

- An Apple silicon Mac
- [Homebrew](https://brew.sh/)
- Lima 2.2 or later
- Ansible
- [1Password CLI](https://developer.1password.com/docs/cli/) for GitHub Credential Enrollment

Install the host tools:

```bash
brew install lima ansible
brew install --cask 1password-cli
```

The host commands check their own prerequisites but do not install or change macOS software.

## Host configuration

Tell Proteus which 1Password field contains the fine-grained GitHub personal access token:

```bash
./configure
```

Enter the field's 1Password secret reference when prompted. Proteus stores the reference, not the token, in `${XDG_CONFIG_HOME:-$HOME/.config}/proteus/config`. It treats the reference as opaque text and does not contact 1Password. Run `./configure` again to accept the current reference or replace it.

The `op` command is not needed while configuring the reference. It is required later when Credential Enrollment resolves that reference.

## Operating workflow

Run these commands from the repository root. Lima owns the VM lifecycle; Provisioning never creates, starts, stops, or deletes a VM.

| Operation | Command |
| --- | --- |
| Create Proteus from the VM Definition | `limactl create --name=proteus ./vm/proteus.yaml` |
| Start Proteus | `limactl start proteus` |
| Apply Provisioning | `./provision` |
| Enroll the configured GitHub credential | `./enroll github` |
| Open a guest shell | `limactl shell proteus` |
| Stop Proteus | `limactl stop proteus` |
| Delete a stopped Proteus VM | `limactl delete proteus` |

Create, start, and provision the VM before first use. On later days, start it and open a shell. Put repositories under `~/projects` inside the guest.

`./provision` and `./enroll github` accept an optional instance name and target `proteus` by default. The selected instance must already exist and be running. Neither command changes its lifecycle state. For example:

```bash
./provision proteus-acceptance-example
./enroll github proteus-acceptance-example
```

## Rebuild Proteus

Deleting Proteus permanently removes its repositories, uncommitted work, VM-Local Credentials, Host-Injected Credentials, and other guest state. After preserving anything you need, run:

```bash
limactl stop proteus
limactl delete proteus
limactl create --name=proteus ./vm/proteus.yaml
limactl start proteus
./provision
./enroll github
limactl shell proteus
```

Then clone your repositories and repeat any other Credential Enrollment. This restores the Development Baseline and the selected GitHub credential, not the rest of the deleted VM's contents.

## Credential Enrollment

After Provisioning, enroll the fine-grained GitHub personal access token selected by `./configure`:

```bash
./enroll github
limactl shell proteus
```

Enrollment asks `op read` to resolve the configured 1Password reference and lets 1Password handle authentication, unlocking, and account selection. The token is streamed to the running guest through standard input. Proteus does not put it in command arguments, environment forwarding, a host file, or terminal output. The command fails if the instance is missing, stopped, or has not been provisioned, and it never creates, starts, stops, deletes, or provisions an instance.

The guest validates the token before atomically replacing `~/.local/share/proteus/secrets/github-token`. The secrets directory is private to the guest user and the token file has mode `0600`. The token is stored as data, not shell code. A stopped VM retains it; deleting the VM removes it with the guest disk.

New interactive Bash sessions read the file and export `GH_TOKEN`. Commands launched from those shells inherit the token, including GitHub CLI and Git's GitHub CLI credential helper for HTTPS operations. Proteus does not export it system-wide, to services, or deliberately to non-interactive Bash commands. The guest's primary user and guest root can read the installed token.

The guest receives only this selected Host-Injected Credential. It cannot invoke 1Password, browse the vault, or retrieve another host credential. Continue to create AWS, cloud, Claude Code, OpenCode, T3 Code, and other credentials inside the guest only when needed.

Set Git identity in the guest-local file included by the Managed Dotfiles Git configuration:

```bash
git config --file ~/.gitconfig.local user.name "Your Name"
git config --file ~/.gitconfig.local user.email "you@example.com"
```

To verify the complete flow manually on macOS, create and start a fresh VM, run `./provision`, run `./enroll github`, and enter a new guest shell. Confirm `gh auth status` and one HTTPS Git operation succeed. Do not print or inspect the token.

## Manual acceptance

Run the real macOS-to-Lima acceptance check manually:

```bash
make lima-acceptance
```

The check validates the production VM Definition, creates and starts a uniquely named `proteus-acceptance-*` VM, and invokes the production Provisioning command once. Fresh-VM Provisioning's exit status is the behavioral assertion. Setup or cleanup failures also fail the command. The check does not run Provisioning a second time or test exact convergence.

The check refuses to adopt an existing instance and deletes the VM it created after success or failure. It disables development-port forwarding for that VM, so the normal `proteus` instance may remain running.

See [`vm/README.md`](./vm/README.md) for the isolation boundary, Docker privilege, and port forwarding.
