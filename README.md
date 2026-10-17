# Proteus

Proteus is a Rebuildable Dev VM for personal development on Apple silicon Macs, managed with Lima and Ansible. It provides development tools and dotfiles while isolating the guest from host directories and macOS credentials. Credentials are enrolled explicitly after Provisioning.

## Quick start

On an Apple silicon Mac with [Homebrew](https://brew.sh/), run these commands from the repository root in an interactive macOS terminal. Proteus requires Lima 2.2 or later. For GitHub enrollment, store a fine-grained personal access token and a dedicated SSH signing key in 1Password, and enter their field references when `./configure` prompts you. Register the public key with GitHub as a signing key once; enrollment restores the same key after a rebuild. See [Credentials](./docs/credentials.md#github). At its Salesforce login URL prompt, press Enter unless your org requires its My Domain URL.

```bash
# Install host tools
brew install lima ansible
brew install --cask 1password-cli

# Configure 1Password references for GitHub access and signing, and the Salesforce login URL
./configure

# Create, start, and provision the VM
limactl create --name=proteus ./vm/proteus.yaml
limactl start proteus
./provision

# Enroll credentials for the tools you use
./enroll github
./enroll claude
./enroll t3
./enroll salesforce
./enroll twg

# Enter the VM
limactl shell proteus
```

Keep repositories under `~/projects` inside the guest. Deleting the VM during a rebuild removes guest files and credentials, so preserve any work you need first.

## Documentation

- [Usage](./docs/usage.md): requirements, host configuration, daily commands, Git identity, and rebuilding
- [Credentials](./docs/credentials.md): GitHub, Claude Code, T3, Salesforce, and Teamwork Graph enrollment
- [Provisioning](./docs/provisioning.md): installed tools, updates, dotfiles, and what a rebuild restores
- [Testing](./docs/testing.md): automated checks and manual acceptance
- [VM details](./vm/README.md): isolation, Docker privileges, and port forwarding
