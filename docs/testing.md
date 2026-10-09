# Testing Proteus

Run these commands from the repository root.

## Automated checks

Run `make static test` to validate Provisioning and the VM Definition and exercise Credential Enrollment with simulated CLI tools. The enrollment tests use separate host and guest homes and a real terminal without contacting 1Password or Claude.

## Manual acceptance

Run the real macOS-to-Lima acceptance check manually:

```bash
make lima-acceptance
```

The check validates the production VM Definition, creates and starts a uniquely named `proteus-acceptance-*` VM, and invokes the production Provisioning command once. Fresh-VM Provisioning's exit status is the behavioral assertion. Setup or cleanup failures also fail the command. The check does not run Provisioning a second time or test exact convergence.

The check refuses to adopt an existing instance and deletes the VM it created after success or failure. It disables development-port forwarding for that VM, so the normal `proteus` instance may remain running.

To verify GitHub Credential Enrollment manually on macOS, create and start a fresh VM, run `./provision`, run `./enroll github`, and enter a new guest shell. Confirm `gh auth status` and one HTTPS Git operation succeed. Do not print or inspect the token.

Run `./enroll claude` from an interactive terminal, complete browser authorization, and confirm `claude auth status` succeeds inside the guest. Stop and start the VM to confirm the login persists. Repeat enrollment after a rebuild.

See [Credential Enrollment](./credentials.md) for authentication details and [VM details](../vm/README.md) for the isolation boundary, Docker privilege, and port forwarding.
