# Operating Proteus

Proteus is a persistent Credential-Isolated Dev VM. Its Lima instance is named `proteus`. It runs Ubuntu 26.04 on ARM64 with no host filesystem mounts, imported host SSH public keys, or forwarded host SSH agent.

## Create the VM

Install Lima on the Mac if needed:

```bash
brew install lima
```

Start the VM:

```bash
limactl start --name=proteus ./vm/proteus.yaml
```

Install the development tools inside the VM:

```bash
limactl shell proteus < ./vm/bootstrap.sh
```

The bootstrap is safe to re-run if it stops halfway through.

Enter the VM:

```bash
limactl shell proteus
```

Repos should live inside the VM, under `~/projects`.

## Manual identity setup

Do not copy SSH keys, GitHub tokens, AWS files, or cloud credentials from the Mac.

Generate a VM-local GitHub SSH key inside the VM:

```bash
ssh-keygen -t ed25519 -C "proteus-github"
```

Add the public key to GitHub, then authenticate GitHub CLI inside the VM:

```bash
gh auth login
```

Configure Git identity manually inside the VM:

```bash
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

The bootstrap does not configure AWS access. When access becomes necessary, enroll AWS SSO inside the VM instead of copying host credentials.

## Docker risk

The bootstrap adds the VM user to the `docker` group. That makes `docker` usable without `sudo`, but the `docker` group is effectively root inside the VM.

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
