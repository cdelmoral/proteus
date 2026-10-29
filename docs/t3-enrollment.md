# T3 Enrollment design

Enrollment invokes `~/.local/bin/t3` directly, without `mise exec` or a Node PATH override. Project Node selection cannot block CLI invocation, and children retain the caller's PATH. See [CLI installation and update ownership](./provisioning.md).

The decisions below are implemented by `./enroll t3` and the guest's `proteus-enroll-t3` helper. Completion checks were simplified after internal startup checks rejected a working service. See [the operating guide](./credentials.md#t3-code) for usage and recovery.

## Settled decisions

- `./enroll t3 [instance-name]` will authorize T3 Connect, link the environment, and install its persistent background service. The intended outcome is a server that starts when the VM boots and continues after the guest user logs out.
- Authorization alone does not complete T3 Enrollment. Service setup failure must report incomplete setup even when authorization has succeeded.
- Provider Credential Enrollment remains separate. A reachable T3 environment without an authenticated provider can still have completed T3 Enrollment.
- Provisioning continues to update only the standalone CLI. Service runtime upgrades and restarts remain explicit operations managed through T3's commands; Provisioning must not interrupt an enrolled service.
- Failed enrollment preserves completed authorization and linking steps. It reports what remains incomplete so a retry can resume without automatically revoking existing access.
- Completion requires saved authorization and environment linking reported by T3 Connect, plus a systemd service that is active, enabled for boot, and persistent after logout. Remote access is verified by connecting from another device.
- Rebuild instructions will document manual deregistration of the old cloud environment and fresh enrollment of the replacement VM. Proteus does not automate cloud registration cleanup.
- Repeated enrollment verifies a completed setup without changing a healthy running server or its runtime. Incomplete enrollment resumes missing authorization or environment linking, while service repair and foreground-server takeover require explicit action. A healthy service may use a different version from the newly provisioned standalone CLI.
- Verification uses the provisioned CLI's saved Connect state and systemd properties. It does not compare link-file timestamps, poll for live linking/startup, validate the pinned runtime, or require that runtime's relay-client version to match the provisioned CLI's expectations.
- Enrollment automatically enables lingering for the guest user when necessary, using guest sudo only for that administrator step. T3 commands always run as the normal guest user. A failed prerequisite produces an incomplete-setup result and recovery instructions.

## Operating boundary

The command follows the existing enrollment interface: it runs from an interactive macOS terminal, defaults to `proteus`, and accepts an optional instance name. The selected VM must already exist, be running, and have the required tools installed. Enrollment does not create, start, stop, delete, or provision the VM.

Credentials and T3 state stay in the guest. Browser approval does not require copying host credentials or exposing the host credential store. Provisioning continues to install the CLI without configuring remote access or a service. See [the service ownership decision](./adr/0003-activate-t3-service-during-enrollment.md).

## Verified constraints

Project Node selection for background agent commands, including the explicit
entrypoint for services with an older runtime-first PATH, is described in
[Node operations](./node-versions.md#background-commands-and-existing-t3-services).
Provisioning exposes project commands without changing the enrolled service.
Any persistent service PATH migration and restart remain explicit operations.

The original integration was verified against T3 v0.0.45. Its [Connect onboarding](https://github.com/pingdotgg/t3code/blob/v0.0.45/apps/server/src/cli/connect.ts) can return successfully when relay-client installation is declined. [Service onboarding](https://github.com/pingdotgg/t3code/blob/v0.0.45/apps/server/src/cli/service.ts) also recovers service-installation errors and offers a manual server command. The wrapper therefore checks saved Connect configuration and systemd persistence after onboarding instead of relying on its exit code alone.

`t3 connect status --json` reports persisted state. Its authentication and linking fields do not prove live credential validity or client connectivity. [The user documentation](https://github.com/pingdotgg/t3code/blob/main/docs/user/remote-access.md#t3-connect-troubleshooting) explicitly distinguishes this status from reachability.

The Linux service requires a systemd user manager and lingering. Enrollment enables lingering when necessary and verifies it before setup; permission failures require an administrator recovery command.

The service uses a [separate, pinned runtime](https://github.com/pingdotgg/t3code/blob/v0.0.45/apps/server/src/cloud/pinnedRuntime.ts). Updating the standalone CLI during Provisioning does not itself update the running service.

Connect writes the desired link configuration, but an already-running service can require a restart to apply it. [Connect](https://github.com/pingdotgg/t3code/blob/v0.0.45/apps/server/src/cli/connect.ts) does not automatically restart an installed, current service; [server startup](https://github.com/pingdotgg/t3code/blob/v0.0.45/apps/server/src/server.ts) applies the desired link. Enrollment reports local completion when saved configuration and service persistence pass. It leaves restart decisions to remote-access verification and explicit recovery, rather than inferring activation from file timestamps.

[Service repair](https://github.com/pingdotgg/t3code/blob/v0.0.45/apps/server/src/cloud/bootService.ts) can stop and restart an existing service. A foreground server is not automatically adopted by the service installer. The wrapper must check for these situations before invoking an onboarding path that could interrupt existing work.

## Implementation and acceptance

Implement the agreed behavior as a separate change to `enroll`, with the corresponding usage, credential, provisioning, and testing documentation. Tests should cover guest-only state, terminal requirements, custom instances, missing prerequisites, preserved partial state, misleading successful onboarding exit codes, and protection of existing servers. Verify enrollment completion independently of the human-readable onboarding output.

Manual acceptance on a fresh provisioned Lima VM must confirm browser authorization, service startup, connection from another device, continued availability after closing the guest shell, and automatic startup after a VM stop/start. Also verify repeat enrollment, a service version differing from the standalone CLI, completion after saving a link while the service is running, explicit recovery if remote access needs a restart, and fresh enrollment after a rebuild.

No design decisions remain open. Automated checks exercise the implementation with simulated T3 and systemd tools; real macOS-to-Lima and remote-client acceptance remains a manual check.
