# Proteus

Proteus is a Rebuildable Dev VM for personal development on Apple silicon Macs, managed with Lima and Ansible. It provides development tools and dotfiles while isolating the guest from host directories and macOS credentials. Credentials are enrolled explicitly after Provisioning.

## Quick start

On an Apple silicon Mac with [Homebrew](https://brew.sh/), run these commands from the repository root in an interactive macOS terminal. Proteus requires Lima 2.2 or later. For GitHub enrollment, have a fine-grained personal access token stored in 1Password and enter its field's secret reference when `./configure` prompts you.

```bash
# Install host tools
brew install lima ansible
brew install --cask 1password-cli

# Configure the 1Password reference for your GitHub token
./configure

# Create, start, and provision the VM
limactl create --name=proteus ./vm/proteus.yaml
limactl start proteus
./provision

# Enroll credentials for the tools you use
./enroll github
./enroll claude

# Enter the VM
limactl shell proteus
```

Keep repositories under `~/projects` inside the guest. Deleting the VM during a rebuild removes guest files and credentials, so preserve any work you need first.

## Documentation

- [Usage](./docs/usage.md): requirements, host configuration, daily commands, Git identity, and rebuilding
- [Credentials](./docs/credentials.md): GitHub and Claude Code enrollment
- [Provisioning](./docs/provisioning.md): installed tools, updates, dotfiles, and what a rebuild restores
- [Testing](./docs/testing.md): automated checks and manual acceptance
- [VM details](./vm/README.md): isolation, Docker privileges, and port forwarding
