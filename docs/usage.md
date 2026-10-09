# Using Proteus

Proteus uses the Lima instance named `proteus`. Normal work returns to the same VM; when it becomes broken or cluttered, replace it from the VM Definition and run Provisioning again.

Run host commands from the repository root. Run the Git identity commands inside a guest shell.

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
| Authorize Claude Code inside the guest | `./enroll claude` |
| Open a guest shell | `limactl shell proteus` |
| Stop Proteus | `limactl stop proteus` |
| Delete a stopped Proteus VM | `limactl delete proteus` |

Create, start, and provision the VM before first use. On later days, start it and open a shell. Put repositories under `~/projects` inside the guest.

`./provision` and both `./enroll` commands accept an optional instance name and target `proteus` by default. The selected instance must already exist and be running. Neither command changes its lifecycle state. For example:

```bash
./provision proteus-acceptance-example
./enroll github proteus-acceptance-example
./enroll claude proteus-acceptance-example
```

## Git identity

Set Git identity in the guest-local file included by the Managed Dotfiles Git configuration:

```bash
git config --file ~/.gitconfig.local user.name "Your Name"
git config --file ~/.gitconfig.local user.email "you@example.com"
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
./enroll claude
limactl shell proteus
```

Then clone your repositories and repeat any other Credential Enrollment. This restores the Development Baseline and the selected GitHub credential, not the rest of the deleted VM's contents.

See [Credential Enrollment](./credentials.md) for authentication details and [Provisioning](./provisioning.md) for the Development Baseline.
