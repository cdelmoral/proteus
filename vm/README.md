# Proteus VM details

The [usage guide](../docs/usage.md#operating-workflow) is the single operating guide for creating, starting, provisioning, entering, stopping, deleting, and rebuilding Proteus.

## Isolation boundary

The VM Definition creates Proteus as a Credential-Isolated Dev VM:

- Host directories are not mounted.
- The host SSH agent is not forwarded.
- Host SSH public keys are not imported.
- Repositories, VM-Local Credentials, and installed Host-Injected Credentials stay on the VM disk.
- Development ports bind to host localhost by default.

Provisioning runs from macOS through Lima's generated SSH configuration. This connection lets Ansible apply the Development Baseline without giving the guest access to macOS credentials. GitHub Credential Enrollment is a separate host command that sends the selected token and Git signing key through standard input after 1Password resolves their configured references. The guest cannot invoke 1Password or access unrelated host credentials.

The installed GitHub token and unencrypted Git signing key are readable by the guest user and guest root. Processes launched from a new interactive Bash session inherit the token as `GH_TOKEN`. Git's managed GitHub credential helper and the managed `gh` launcher also read the token when needed, allowing HTTPS Git and GitHub CLI commands from background services without exporting it into the service's environment. Git uses the signing key directly without a host SSH agent. This boundary protects the host credential store and ambient host credentials, not credentials deliberately installed in the guest. See the [Credential Enrollment guide](../docs/credentials.md) for the enrollment procedure.

## Docker risk

Provisioning adds the VM user to the `docker` group. This permits Docker commands without `sudo`, but it also grants root-level control inside the VM.

Proteus is a single-user VM and must not assume a Production AWS Role under this security model. The only production Salesforce identity it may hold is a Dev Hub User credential, enrolled with `./enroll salesforce` so scratch orgs can be created; see [ADR 0004](../docs/adr/0004-allow-dev-hub-user-credential.md). This exception does not relax the Production AWS Role rule. Revisit the design if the VM becomes multi-user, stores sensitive data, or needs a Production AWS Role.

## Ports

The VM Definition forwards these guest ports to localhost on the Mac:

- `127.0.0.1:3000`
- `127.0.0.1:5173`
- `127.0.0.1:8000`
- `127.0.0.1:8080`
- `127.0.0.1:1717`, Salesforce CLI's OAuth callback, which is only listened on during `./enroll salesforce`

Lima also automatically forwards other TCP ports that guest processes listen on to the same port on host localhost. The explicit rules keep the ports above forwarded regardless of that default.

To expose one port to selected devices on the local network, stop Proteus and change that port's `hostIP` in `vm/proteus.yaml` to `"0.0.0.0"`:

```yaml
portForwards:
  - guestPort: 5173
    hostPort: 5173
    hostIP: "0.0.0.0"
```

Some development servers listen only on guest localhost by default. Configure the server to listen on all guest interfaces when LAN access needs it. For Vite, pass `--host 0.0.0.0`.

Change `hostIP` back to `"127.0.0.1"` when LAN testing is done.
