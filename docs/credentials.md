# Credential Enrollment

Run enrollment commands from the repository root on macOS after creating, starting, and provisioning the VM. See the [usage guide](./usage.md#operating-workflow) for those commands and for targeting another instance.

## GitHub

After Provisioning, enroll the fine-grained GitHub personal access token selected by `./configure`:

```bash
./enroll github
limactl shell proteus
```

Enrollment asks `op read` to resolve the configured 1Password reference and lets 1Password handle authentication, unlocking, and account selection. The token is streamed to the running guest through standard input. Proteus does not put it in command arguments, environment forwarding, a host file, or terminal output. The command fails if the instance is missing, stopped, or has not been provisioned, and it never creates, starts, stops, deletes, or provisions an instance.

The guest validates the token before atomically replacing `~/.local/share/proteus/secrets/github-token`. The secrets directory is private to the guest user and the token file has mode `0600`. The token is stored as data, not shell code. A stopped VM retains it; deleting the VM removes it with the guest disk.

Managed Dotfiles configure Git's HTTPS credential helper for `github.com` and `gist.github.com`. The helper reads the enrolled token each time Git requests credentials and passes it to a GitHub CLI subprocess. HTTPS Git operations work in interactive shells, non-interactive commands, and background services such as T3 without requiring `GH_TOKEN` in their environment. Enrollment does not rewrite Managed Dotfiles, so repeating Provisioning preserves this configuration. Token replacement takes effect on the next Git operation without restarting a service.

New interactive Bash sessions also read the file and export `GH_TOKEN` for direct GitHub CLI commands. Proteus does not export it system-wide or into a service's environment. The guest's primary user and guest root can read the installed token.

If T3 reports `could not read Username for 'https://github.com': terminal prompts disabled` after switching to its background service, apply the updated Managed Dotfiles with `./provision` from macOS. Run `./enroll github` if the guest has not enrolled its GitHub token, then retry the clone in T3. No T3 service restart is required.

The guest receives only this selected Host-Injected Credential. It cannot invoke 1Password, browse the vault, or retrieve another host credential. Continue to create AWS, cloud, OpenCode, T3 Code, and other credentials inside the guest only when needed.

## Claude Code

After Provisioning, run this command from an interactive macOS terminal:

```bash
./enroll claude
```

Proteus runs `claude auth login` inside the guest using its managed Node runtime. Open the generated login URL in your macOS browser and authorize access. If the browser returns a code, paste it into the waiting terminal. This is Claude Code's documented [manual login flow](https://code.claude.com/docs/en/authentication#log-in-to-claude-code) for sessions where the browser cannot reach the local callback server.

Enrollment requires terminal input and output; piping input or redirecting output fails before login starts. It does not need 1Password or a configured GitHub credential source. The selected instance must already be running and provisioned with Claude Code. Enrollment never starts or provisions it. Proteus reports success only after login succeeds and `claude auth status` confirms authentication.

Claude Code owns storage and renewal of the resulting VM-Local Credential. Using the host browser for authorization does not expose its cookies or credential store to the guest. Proteus does not copy a host Claude credential or capture the returned code. The credential persists across VM stops, is removed when the VM is deleted, and must be enrolled again after a rebuild. Run `./enroll claude` again when Claude Code requires a new login.

## T3 Code

After Provisioning, run this command from an interactive macOS terminal:

```bash
./enroll t3
```

On a fresh guest, Proteus runs `t3 connect --headless` using the managed runtime. Accept T3's relay-client and background-service installation prompts. Open its authorization URL in your macOS browser, confirm the short code, and approve access. T3 completes authorization inside the guest without an OAuth callback port forward. It owns storage and renewal of the resulting VM-Local Credential; Proteus does not copy host T3 credentials or capture the authorization code. This is T3's documented [remote sign-in flow](https://github.com/pingdotgg/t3code/blob/main/docs/user/remote-access.md#t3-connect).

Enrollment requires terminal input and output and an already running, provisioned instance. It does not need 1Password or the configured GitHub credential source, and never changes the VM lifecycle. Provider Credential Enrollment is separate: run `./enroll claude` when using Claude through T3.

T3 installs a systemd user service with its own pinned runtime. Proteus enables lingering for the guest user when needed, using guest sudo only for that step. The server starts when the VM boots and continues after the guest shell closes. The VM must remain running and the Mac awake for availability. Manage the service as the normal guest user:

```bash
t3 service status
t3 service restart
t3 service uninstall
```

Enrollment independently checks saved authorization and link configuration, an available relay client, and a running service enabled for boot and logout persistence. It waits up to 60 seconds for fresh startup and local linking; a slower or failed link reports incomplete setup while leaving completed steps intact. Local verification does not prove live credential validity or connectivity from another device. Sign in to the same T3 Connect account on your other device and choose the environment to test remote access.

Repeated enrollment leaves a completed, healthy setup unchanged, even when its service version differs from the provisioned CLI. Verification uses the service's pinned CLI to avoid treating a newer CLI's relay-client requirements as a broken existing service. If a running service needs authorization, Proteus uses `t3 connect link --headless`, then reports any required restart as incomplete. It never automatically updates, restarts, or takes over an existing server. A foreground server must be stopped explicitly before enrollment. Failed attempts preserve credentials and completed configuration; follow the reported guest recovery instructions and retry.

Provisioning updates the npm CLI without updating or restarting an enrolled service. Service upgrades are explicit operations through T3's commands. [T3's service documentation](https://github.com/pingdotgg/t3code/blob/main/docs/user/background-service.md) describes updates, recovery, and removal. Signing out with `t3 connect logout` clears Connect authorization but does not uninstall the service; `t3 connect unlink` retains the login while disabling exposure.

Deleting the VM removes its local credentials and service. Before a rebuild, deregister its old environment through the account's T3 Connect page; you can also deregister an already wiped environment. Forgetting it in a device's connection list is insufficient. Enroll the replacement VM afresh; Proteus does not automate cloud deregistration.

The helper follows the T3 v0.0.45 status and runtime formats and rejects unrecognized state rather than reporting success. It uses the guest's `T3CODE_HOME`, or `~/.t3` by default, and refuses to replace an existing service configured for another data directory. Run recovery commands with the same data directory when using a custom one.

See [host configuration](./usage.md#host-configuration) to select the GitHub token source, and [VM details](../vm/README.md#isolation-boundary) for the isolation boundary.
