# Testing Proteus

Run these commands from the repository root.

## Automated checks

Run `make static test` to validate Provisioning and the VM Definition and exercise enrollment with simulated CLI tools. The enrollment tests use separate host and guest homes and a real terminal without contacting 1Password, Claude, or T3 Connect. T3 tests simulate systemd, lingering, and provider-independent Connect setup, including partial failures, retries, and existing-server protection. They verify completion from saved Connect configuration and systemd persistence, including links saved after startup and healthy services without private runtime metadata. GitHub credential tests require Git and GitHub CLI and exercise real Git credential lookup with dummy tokens, without network access. They cover background-service environments, reprovisioning, token rotation, and missing credentials.

## Manual acceptance

Run the real macOS-to-Lima acceptance check manually:

```bash
make lima-acceptance
```

The check validates the production VM Definition, creates and starts a uniquely named `proteus-acceptance-*` VM, and invokes the production Provisioning command once. Fresh-VM Provisioning's exit status is the behavioral assertion. Setup or cleanup failures also fail the command. The check does not run Provisioning a second time or test exact convergence.

The check refuses to adopt an existing instance and deletes the VM it created after success or failure. It disables development-port forwarding for that VM, so the normal `proteus` instance may remain running.

To verify GitHub Credential Enrollment manually on macOS, create and start a fresh VM, run `./provision`, run `./enroll github`, and enter a new guest shell. Confirm `gh auth status` and one HTTPS Git operation succeed. Repeat the Git operation through a non-interactive guest command with `GH_TOKEN` and `GITHUB_TOKEN` unset, and again after Provisioning. Confirm a private project clone through T3's background service succeeds. Do not print or inspect the token.

Run `./enroll claude` from an interactive terminal, complete browser authorization, and confirm `claude auth status` succeeds inside the guest. Stop and start the VM to confirm the login persists. Repeat enrollment after a rebuild.

For T3, run `./enroll t3` on a fresh provisioned VM from an interactive macOS terminal. Accept relay-client and service installation, approve the browser code, and confirm local verification completes. Sign in to the same T3 Connect account from another device and connect to the environment. Close the guest shell, then stop/start the VM; confirm the service and remote access return without running enrollment again. Authenticate a provider separately to run agent work.

Repeat T3 enrollment and confirm it leaves the running service untouched. Verify that a service on a different version from the npm CLI still passes when healthy. Decline or interrupt setup, confirm incomplete setup is reported, and retry using the saved authorization. Start a foreground server and confirm enrollment refuses takeover. For a running service started before Connect was enabled, confirm enrollment saves authorization and environment linking without restarting it or rejecting the new link's timestamp. Verify remote access from another device; if activation needs a restart, perform it explicitly when ready. After deleting the VM, deregister its old cloud environment and enroll the replacement afresh.

See [Credential Enrollment](./credentials.md) for authentication details and [VM details](../vm/README.md) for the isolation boundary, Docker privilege, and port forwarding.
