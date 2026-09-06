# Proteus

Proteus is a persistent, general-purpose Linux development VM for macOS. It runs on [Lima](https://lima-vm.io/) and keeps development credentials separate from the host.

Projects, tools, and credentials live on the VM disk. Proteus does not mount host directories, import host SSH public keys, or forward the host SSH agent. Create GitHub and cloud credentials inside the VM instead of copying them from macOS.

## Requirements

- An Apple silicon Mac
- [Homebrew](https://brew.sh/)
- Lima

Install Lima if needed:

```bash
brew install lima
```

## Start Proteus

Create and start the VM from the repository root:

```bash
limactl start --name=proteus ./vm/proteus.yaml
```

Install the development tools:

```bash
limactl shell proteus < ./vm/bootstrap.sh
```

## Provisioning modes

Routine Ansible Provisioning reconciles the checked-in package and tool versions without requesting an Ubuntu package upgrade:

```bash
./provision
```

Request safe Ubuntu package upgrades explicitly:

```bash
./provision --upgrade
```

Upgrade mode does not discover new mise, Node, or pnpm releases. Change their checked-in versions before Provisioning can install a newer release.

Enter the VM:

```bash
limactl shell proteus
```

Clone repositories under `~/projects`. Credentials created inside Proteus persist with the VM disk.

See [`vm/README.md`](./vm/README.md) for identity setup, Docker security, and port forwarding.

## Isolation boundary

Proteus isolates credentials by configuration and working practice:

- Host directories are not mounted into the VM.
- The host SSH agent is not forwarded.
- Host SSH public keys are not imported.
- Repositories and credentials stay on the VM disk.
- Forwarded development ports listen on host localhost by default.

Proteus has passwordless `sudo`, and its user belongs to the `docker` group. Either grants root-level control inside the VM. Do not give Proteus a Production AWS Role without reviewing this security model.
