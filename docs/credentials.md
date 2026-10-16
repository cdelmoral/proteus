# Credential Enrollment

Run enrollment commands from the repository root on macOS after creating, starting, and provisioning the VM. See the [usage guide](./usage.md#operating-workflow) for those commands and for targeting another instance.

## GitHub

Before first enrollment, store a fine-grained GitHub personal access token and a dedicated Ed25519 SSH signing key in 1Password. Create the SSH Key item in 1Password and add its public key to GitHub with key type **Signing Key**. This is a one-time step for each key; enrollment does not register keys or check their GitHub registration. See [1Password's SSH key guide](https://developer.1password.com/docs/ssh/manage-keys/) and [GitHub's registration guide](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/adding-a-new-ssh-key-to-your-github-account).

Run `./configure` and supply the token field's reference and the SSH item's private-key field reference. If you previously configured only a token, run `./configure` again to add the signing-key reference. After Provisioning, enroll both credentials:

```bash
./enroll github
limactl shell proteus
```

Enrollment asks `op read` to resolve both configured 1Password references on macOS and lets 1Password handle authentication, unlocking, and account selection. It requests the private key in OpenSSH format, resolves both credentials before transferring either, and streams the token followed by the multiline key to the running guest through standard input. Proteus does not put the secrets in command arguments, environment forwarding, host files, or terminal output. The command fails if the instance is missing, stopped, or has not been provisioned, and it never creates, starts, stops, deletes, or provisions an instance.

The guest derives the SSH public key and validates the token before replacing installed credentials. A missing, malformed, or passphrase-protected key or rejected token leaves the installed credentials unchanged. The files are installed individually without rollback across the whole enrollment; if a later installation or Git configuration step fails, correct the reported problem and rerun enrollment.

The token is stored at `~/.local/share/proteus/secrets/github-token`, the private key at `~/.local/share/proteus/secrets/git-signing-key`, and the derived public key at the same path with `.pub` appended. The secrets directory is private to the guest user and the files have mode `0600`. A stopped VM retains them; deleting the VM removes the guest copies.

Enrollment updates only `gpg.format`, `gpg.ssh.program`, `user.signingKey`, and `commit.gpgSign` in `~/.gitconfig.local`, preserving the existing Git identity and unrelated settings. Git signs commits by default using the private key directly through `ssh-keygen`, without an SSH agent or interactive unlock. Enrollment does not create a test commit or verify signatures. Provisioning preserves the credentials and guest-local Git configuration, and repeating enrollment replaces the selected token and signing key without restarting T3.

The guest holds an unencrypted working copy so background processes can sign. Use a key dedicated to Proteus commit signing and register it only for signing. The guest user and guest root can read the key and use it outside 1Password. Rebuilds reuse the same GitHub registration; deleting a VM does not invalidate any copies of its key. To rotate it, replace the key in 1Password, update GitHub's signing-key registration, and enroll again.

Managed Dotfiles configure Git's HTTPS credential helper for `github.com` and `gist.github.com`. The helper reads the enrolled token each time Git requests credentials and passes it to a GitHub CLI subprocess. HTTPS Git operations work in interactive shells, non-interactive commands, and background services such as T3 without requiring `GH_TOKEN` in their environment. Enrollment does not rewrite Managed Dotfiles, so repeating Provisioning preserves this configuration. Token replacement takes effect on the next Git operation without restarting a service.

Managed Dotfiles also install a `gh` launcher, exposed through `/usr/local/bin/gh` so background services can find it on the normal system PATH. When neither `GH_TOKEN` nor `GITHUB_TOKEN` is set, the launcher reads the enrolled token and passes it to the packaged `/usr/bin/gh` executable. Each invocation reads the current credential, so background GitHub CLI commands work immediately after enrollment or token replacement without restarting T3. Explicit environment tokens take precedence; with no enrolled token, normal GitHub CLI behavior is preserved.

New interactive Bash sessions continue to read the file and export `GH_TOKEN`. Proteus does not export it system-wide or into a service's environment; the launcher supplies it only to the GitHub CLI process. The guest's primary user and guest root can read the installed token. Calling `/usr/bin/gh` directly bypasses the launcher.

If Git or GitHub CLI commands in T3 cannot authenticate after switching to its background service, apply the updated Managed Dotfiles and launcher with `./provision` from macOS. Run `./enroll github` if the guest has not enrolled its GitHub token, then retry the command in T3. No T3 service restart is required.

The guest receives only these selected Host-Injected Credentials. It cannot invoke 1Password, browse the vault, or retrieve another host credential. Continue to create AWS, cloud, OpenCode, T3 Code, Salesforce, and other credentials inside the guest only when needed.

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

Enrollment checks saved authorization and environment linking through `t3 connect status --json`, then verifies that systemd reports the service active and enabled for boot, with lingering enabled for logout persistence. It does not compare link-file timestamps, wait for server runtime files, or inspect the pinned runtime. Local completion does not prove live credential validity or connectivity from another device. Sign in to the same T3 Connect account on your other device and choose the environment to verify remote access.

Repeated enrollment leaves a completed, healthy setup unchanged, even when its service version differs from the provisioned CLI. The provisioned CLI reports saved Connect configuration; its relay-client version requirements do not determine enrollment completion. If a running service needs authorization or environment linking, Proteus uses `t3 connect link --headless` and verifies the saved result. It never automatically updates, restarts, or takes over an existing server. Before setup that could affect an existing server, the helper checks the server runtime file and refuses foreground-server takeover. Failed attempts preserve credentials and completed configuration; follow the reported guest recovery instructions and retry.

If enrollment completes but remote access fails, inspect `t3 connect status`, `t3 service status`, and the service log in the guest. Newly saved authorization or link configuration may require `t3 service restart` when you can interrupt current work. Enrollment does not infer that requirement from file timestamps.

Provisioning updates the npm CLI without updating or restarting an enrolled service. Service upgrades are explicit operations through T3's commands. [T3's service documentation](https://github.com/pingdotgg/t3code/blob/main/docs/user/background-service.md) describes updates, recovery, and removal. Signing out with `t3 connect logout` clears Connect authorization but does not uninstall the service; `t3 connect unlink` retains the login while disabling exposure.

Deleting the VM removes its local credentials and service. Before a rebuild, deregister its old environment through the account's T3 Connect page; you can also deregister an already wiped environment. Forgetting it in a device's connection list is insufficient. Enroll the replacement VM afresh; Proteus does not automate cloud deregistration.

The helper expects the `desired`, `authenticated`, and `linked` boolean fields from T3 Connect status. It uses the guest's `T3CODE_HOME`, or `~/.t3` by default, and refuses to replace an existing service configured for another data directory. Run recovery commands with the same data directory when using a custom one.

## Salesforce

After Provisioning, run this command from an interactive macOS terminal:

```bash
./enroll salesforce
```

Enrollment authorizes the Dev Hub User, whose minimal permissions allow only scratch org management through Dev Hub. [ADR 0004](./adr/0004-allow-dev-hub-user-credential.md) records why this is the only production Salesforce identity Proteus may hold.

Proteus runs `sf org login web --instance-url <login-url> --alias devhub --set-default-dev-hub` inside the guest, using the Salesforce login URL saved by `./configure`, or `https://login.salesforce.com` when none is saved. The guest has no browser, so Proteus captures Salesforce CLI's authorization URL and prints it. Open it in your macOS browser, log in as the Dev Hub User, complete any MFA or login challenges, and approve access. The browser's redirect to `localhost:1717` reaches Salesforce CLI's callback server in the guest through the VM Definition's port forward. Port 1717 must be free on the Mac while enrollment runs, so do not run another Salesforce CLI web login on the Mac at the same time.

Enrollment requires terminal input and output; piping input or redirecting output fails before login starts. It does not need 1Password or a configured GitHub credential source. The selected instance must already be running and provisioned with Salesforce CLI. Enrollment never starts or provisions it. Proteus reports success only after Salesforce CLI reports the `devhub` authorization as connected. Every run performs a fresh browser login and replaces the saved authorization, so run `./enroll salesforce` again to recover from a revoked or expired login.

The resulting Dev Hub User credential is a VM-Local Credential. Salesforce CLI stores it in its file-based keychain inside the guest; Proteus does not store any Salesforce token on macOS or in 1Password. It persists across VM stops and is removed when the VM is deleted. Because the managed `sf` launcher is on the system PATH and always selects the file-based keychain, interactive shells and background services such as T3 use the same authorization.

`devhub` is the global default Dev Hub, so scratch org commands work without `--target-dev-hub`:

```bash
sf org create scratch --definition-file config/project-scratch-def.json --alias my-scratch
```

Salesforce CLI authorizes each new scratch org inside the guest from the Dev Hub User's authorization, without a browser or another enrollment. To open an org from the guest, print its login URL and open the link on macOS:

```bash
sf org open --target-org my-scratch --url-only
```

`sf org logout` removes only the guest-local authorization; it does not revoke the OAuth token in Salesforce. Before deleting the VM, delete scratch orgs you no longer need with `sf org delete scratch`, then revoke the VM's Salesforce CLI access in the Dev Hub User's personal settings under OAuth Connected Apps. See [rebuilding Proteus](./usage.md#rebuild-proteus).

See [host configuration](./usage.md#host-configuration) to select the GitHub token source and Salesforce login URL, and [VM details](../vm/README.md#isolation-boundary) for the isolation boundary.
