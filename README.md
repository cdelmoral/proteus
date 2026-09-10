# Proteus

Proteus is a persistent, general-purpose Credential-Isolated Dev VM for macOS. It runs on [Lima](https://lima-vm.io/) and keeps development credentials separate from the host.

Projects, tools, and VM-Local Credentials live on the VM disk. Proteus does not mount host directories, import host SSH public keys, or forward the host SSH agent. Create GitHub and cloud credentials inside the VM instead of copying them from macOS.

## Requirements

- An Apple silicon Mac
- [Homebrew](https://brew.sh/)
- Lima 2.2 or later
- Ansible

Install the host tools before creating Proteus:

```bash
brew install lima ansible
```

The Provisioning command checks these prerequisites but does not install or change software on macOS.

## Operating workflow

Run these steps from the repository root.

### 1. Apply the VM Definition

Create and start the VM from the committed VM Definition:

```bash
limactl start --name=proteus ./vm/proteus.yaml
```

### 2. Run Provisioning

Apply all declared software and non-secret configuration:

```bash
./provision
```

Provisioning ends with one read-only smoke phase that checks every baseline component.

### 3. Enter Proteus

```bash
limactl shell proteus
```

Clone repositories under `~/projects`.

### 4. Perform Credential Enrollment

Create the SSH key and GitHub authentication inside Proteus. Configure Git identity in the guest-local `~/.gitconfig.local` file. See [`vm/README.md`](./vm/README.md) for the commands and the future AWS SSO enrollment policy.

The Ansible cutover supports fresh VMs. Recreate a VM configured by the old shell bootstrap before using this workflow. Provisioning does not migrate or adopt bootstrap-created state.

## Provisioning behavior

Routine Provisioning reconciles the checked-in package and tool versions without requesting an Ubuntu package upgrade:

```bash
./provision
```

To provision another running Lima instance, pass its name:

```bash
./provision proteus-acceptance-example
```

Provisioning does not perform general Ubuntu package upgrades. Change checked-in tool versions when the Development Baseline needs a newer release.

Managed Dotfiles live under `dotfiles/home`. Provisioning copies that package into the guest and links it into the home directory with GNU Stow. Git identity stays outside the package in `~/.gitconfig.local`.

The playbook records these maintenance tags: `system`, `development_tools`, `shell`, `dotfiles`, `docker`, `github_cli`, and `smoke`. The `./provision` command deliberately does not expose arbitrary Ansible arguments.

Provisioning fails without changing VM power state when Ansible or Lima is missing, the selected instance does not exist or is stopped, Lima's generated SSH configuration is unreadable, or Ansible reports a failure.

## Disposable Lima acceptance

Run the full macOS-to-guest acceptance check on an Apple silicon Mac with Lima and Ansible installed:

```bash
make lima-acceptance
```

The check validates the production VM Definition, creates a uniquely named `proteus-acceptance-*` instance from it, and disables only that instance's development-port forwards. The normal `proteus` instance may keep running because the disposable VM does not claim ports 3000, 5173, 8000, or 8080.

The check calls `./provision` once against the disposable instance. An exit trap deletes the exact instance created by the check, including when Provisioning fails. It refuses to use an existing name and cannot target the normal `proteus` instance.

See [`vm/README.md`](./vm/README.md) for Credential Enrollment, Docker security, and port forwarding.

## Isolation boundary

Proteus isolates credentials by configuration and working practice:

- Host directories are not mounted into the VM.
- The host SSH agent is not forwarded.
- Host SSH public keys are not imported.
- Repositories and credentials stay on the VM disk.
- Forwarded development ports listen on host localhost by default.

Proteus has passwordless `sudo`, and its user belongs to the `docker` group. Either grants root-level control inside the VM. Do not give Proteus a Production AWS Role without reviewing this security model.
