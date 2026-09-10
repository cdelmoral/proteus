# Operating Proteus

Proteus is a persistent Credential-Isolated Dev VM. Its Lima instance is named `proteus`. It runs Ubuntu 26.04 on ARM64 with no host filesystem mounts, imported host SSH public keys, or forwarded host SSH agent.

## Operating workflow

Install Lima and Ansible on the Mac before operating Proteus:

```bash
brew install lima ansible
```

The Provisioning command checks host prerequisites but never installs or changes macOS software.

### 1. Apply the VM Definition

From the repository root, create and start Proteus from the committed VM Definition:

```bash
limactl start --name=proteus ./vm/proteus.yaml
```

### 2. Run Provisioning

Apply all declared software and non-secret configuration from macOS:

```bash
./provision
```

Provisioning runs one complete read-only smoke phase after applying the system, development tool, shell, Docker, and GitHub CLI configuration. Pass an instance name to target a running instance other than `proteus`, for example `./provision proteus-acceptance-example`.

Provisioning installs the home-shaped package under `dotfiles/home` as one Managed Dotfiles collection with GNU Stow. The package contains non-secret configuration only. Git identity stays in the guest-local `~/.gitconfig.local` file.

The playbook has `system`, `development_tools`, `shell`, `dotfiles`, `docker`, `github_cli`, and `smoke` task tags. Provisioning applies every concern and finishes with its smoke checks. Stow rejects unexpected files at Managed Dotfiles paths instead of replacing them.

Provisioning never starts or stops the VM. It reports an error when a host prerequisite is missing, the instance does not exist or is stopped, Lima's generated SSH configuration is unreadable, or the playbook fails.

To test this workflow through a fresh Lima guest without changing the normal `proteus` instance, run `make lima-acceptance` from the repository root. The disposable acceptance instance uses this production VM Definition and the `./provision` command. Its fixed development-port forwards are disabled so `proteus` can remain running. The check runs Provisioning once and deletes only the temporary `proteus-acceptance-*` instance it created.

### 3. Enter Proteus

```bash
limactl shell proteus
```

Repos should live inside the VM, under `~/projects`.

### 4. Perform Credential Enrollment

Complete the following interactive steps inside Proteus. They create VM-Local Credentials and never copy or forward credentials from macOS.

This cutover supports fresh VMs only. Recreate a VM configured by the old shell bootstrap. Provisioning does not migrate or adopt its state.

## Credential Enrollment

Do not copy SSH keys, GitHub tokens, AWS files, or cloud credentials from the Mac.

Generate a VM-local GitHub SSH key inside the VM:

```bash
ssh-keygen -t ed25519 -C "proteus-github"
```

Add the public key to GitHub, then authenticate GitHub CLI inside the VM:

```bash
gh auth login
```

Configure Git identity manually inside the VM. The stowed main Git configuration includes `~/.gitconfig.local`:

```bash
git config --file ~/.gitconfig.local user.name "Your Name"
git config --file ~/.gitconfig.local user.email "you@example.com"
```

AWS SSO remains future interactive Credential Enrollment. When access becomes necessary, enroll inside the VM instead of copying host credentials.

## Docker risk

Provisioning adds the VM user to the `docker` group. That makes `docker` usable without `sudo`, but the `docker` group is effectively root inside the VM.

This is acceptable because Proteus is a single-user VM and does not assume a Production AWS Role. Revisit this choice if the VM becomes multi-user, stores sensitive data, or needs a Production AWS Role.

## Ports

The default config forwards common dev ports to the Mac only:

- `127.0.0.1:3000`
- `127.0.0.1:5173`
- `127.0.0.1:8000`
- `127.0.0.1:8080`

To expose one port to selected devices on the local network, stop the VM, edit that port in `vm/proteus.yaml`, and change `hostIP` to `"0.0.0.0"`:

```yaml
portForwards:
  - guestPort: 5173
    hostPort: 5173
    hostIP: "0.0.0.0"
```

Start the dev server so it listens beyond guest localhost when the framework requires it. For example, Vite usually needs `--host 0.0.0.0`.

Switch the port back to `127.0.0.1` when LAN testing is done.
