# Proteus VM details

The [main README](../README.md#operating-workflow) is the single operating guide for creating, starting, provisioning, entering, stopping, deleting, and rebuilding Proteus.

## Isolation boundary

The VM Definition creates Proteus as a Credential-Isolated Dev VM:

- Host directories are not mounted.
- The host SSH agent is not forwarded.
- Host SSH public keys are not imported.
- Repositories, VM-Local Credentials, and installed Host-Injected Credentials stay on the VM disk.
- Development ports bind to host localhost by default.

Provisioning runs from macOS through Lima's generated SSH configuration. This connection lets Ansible apply the Development Baseline without giving the guest access to macOS credentials. GitHub Credential Enrollment is a separate host command that sends one token through standard input after 1Password resolves its configured reference. The guest cannot invoke 1Password or access unrelated host credentials.

The installed GitHub token is readable by the guest user and guest root. Processes launched from a new interactive Bash session inherit it as `GH_TOKEN`. This boundary protects the host credential store and ambient host credentials, not a credential deliberately installed in the guest. See the [main README](../README.md#credential-enrollment) for the enrollment procedure.

## Docker risk

Provisioning adds the VM user to the `docker` group. This permits Docker commands without `sudo`, but it also grants root-level control inside the VM.

Proteus is a single-user VM and must not assume a Production AWS Role under this security model. Revisit the design if the VM becomes multi-user, stores sensitive data, or needs a Production AWS Role.

## Ports

The VM Definition forwards these guest ports to localhost on the Mac:

- `127.0.0.1:3000`
- `127.0.0.1:5173`
- `127.0.0.1:8000`
- `127.0.0.1:8080`

To expose one port to selected devices on the local network, stop Proteus and change that port's `hostIP` in `vm/proteus.yaml` to `"0.0.0.0"`:

```yaml
portForwards:
  - guestPort: 5173
    hostPort: 5173
    hostIP: "0.0.0.0"
```

Some development servers listen only on guest localhost by default. Configure the server to listen on all guest interfaces when LAN access needs it. For Vite, pass `--host 0.0.0.0`.

Change `hostIP` back to `"127.0.0.1"` when LAN testing is done.
