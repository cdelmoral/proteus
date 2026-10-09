# Proteus

Proteus is one named, Rebuildable Dev VM for personal development on an Apple silicon Mac. Its Lima instance is named `proteus`. Normal work returns to the same VM; when it becomes broken or cluttered, replace it from the VM Definition and run Provisioning again.

Proteus is also a Credential-Isolated Dev VM. It does not mount host directories, import host SSH public keys, or forward the host SSH agent. Repositories and VM-Local Credentials stay on the VM disk; Proteus cannot access credentials stored on macOS.

## What a rebuild restores

Provisioning applies the Development Baseline: the software and non-secret configuration needed for development. It uses Ansible for system state and tools, then installs `dotfiles/home` as one opaque Managed Dotfiles collection with GNU Stow. Ansible does not manage each application's configuration separately.

The Development Baseline includes command-line development tools, pinned language runtimes, Docker, GitHub CLI, Neovim, Claude Code, OpenCode, T3 Code, and the Managed Dotfiles. Applications may download plugins or create caches and private state when first run after a rebuild.

Each Provisioning run installs pnpm, Claude Code, OpenCode, and T3 Code from their npm `latest` tags, upgrading existing installations when newer releases are available.

A rebuild does not restore VM-Local Credentials, project repositories, uncommitted work, command history, caches, application state, or workspace state. Back up or publish work that must survive before deleting Proteus. Credential Enrollment and repository cloning happen again in the new guest.

T3 Code is installed as a command only. Provisioning does not start it, run a background service, expose a port, pair a client, configure T3 Connect, or choose another connection method.

## Requirements

- An Apple silicon Mac
- [Homebrew](https://brew.sh/)
- Lima 2.2 or later
- Ansible

Install the host tools:

```bash
brew install lima ansible
```

Provisioning checks these prerequisites but does not install or change macOS software.

## Operating workflow

Run these commands from the repository root. Lima owns the VM lifecycle; Provisioning never creates, starts, stops, or deletes a VM.

| Operation | Command |
| --- | --- |
| Create Proteus from the VM Definition | `limactl create --name=proteus ./vm/proteus.yaml` |
| Start Proteus | `limactl start proteus` |
| Apply Provisioning | `./provision` |
| Open a guest shell | `limactl shell proteus` |
| Stop Proteus | `limactl stop proteus` |
| Delete a stopped Proteus VM | `limactl delete proteus` |

Create, start, and provision the VM before first use. On later days, start it and open a shell. Put repositories under `~/projects` inside the guest.

`./provision` accepts zero or one instance name. With no argument it targets `proteus`. To provision another running instance:

```bash
./provision proteus-acceptance-example
```

The selected instance must already exist and be running. Provisioning fails rather than changing its lifecycle state.

## Rebuild Proteus

Deleting Proteus permanently removes its repositories, uncommitted work, VM-Local Credentials, and other guest state. After preserving anything you need, run:

```bash
limactl stop proteus
limactl delete proteus
limactl create --name=proteus ./vm/proteus.yaml
limactl start proteus
./provision
limactl shell proteus
```

Then repeat Credential Enrollment and clone your repositories. This restores the Development Baseline, not the deleted VM's contents.

## Credential Enrollment

Perform Credential Enrollment interactively inside Proteus after Provisioning. Do not copy SSH keys, GitHub tokens, AWS files, cloud credentials, or agent-provider credentials from macOS.

Create a GitHub SSH key as a VM-Local Credential and authenticate GitHub CLI:

```bash
ssh-keygen -t ed25519 -C "proteus-github"
gh auth login
```

Add the generated public key to GitHub. Set Git identity in the guest-local file included by the Managed Dotfiles Git configuration:

```bash
git config --file ~/.gitconfig.local user.name "Your Name"
git config --file ~/.gitconfig.local user.email "you@example.com"
```

Enroll AWS, cloud, Claude Code, OpenCode, T3 Code, and other credentials inside the guest only when needed. Credential Enrollment does not weaken the isolation boundary by importing host credentials.

## Manual acceptance

Run the real macOS-to-Lima acceptance check manually:

```bash
make lima-acceptance
```

The check validates the production VM Definition, creates and starts a uniquely named `proteus-acceptance-*` VM, and invokes the production Provisioning command once. Fresh-VM Provisioning's exit status is the behavioral assertion. Setup or cleanup failures also fail the command. The check does not run Provisioning a second time or test exact convergence.

The check refuses to adopt an existing instance and deletes the VM it created after success or failure. It disables development-port forwarding for that VM, so the normal `proteus` instance may remain running.

See [`vm/README.md`](./vm/README.md) for the isolation boundary, Docker privilege, and port forwarding.
