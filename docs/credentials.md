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

New interactive Bash sessions read the file and export `GH_TOKEN`. Commands launched from those shells inherit the token, including GitHub CLI and Git's GitHub CLI credential helper for HTTPS operations. Proteus does not export it system-wide, to services, or deliberately to non-interactive Bash commands. The guest's primary user and guest root can read the installed token.

The guest receives only this selected Host-Injected Credential. It cannot invoke 1Password, browse the vault, or retrieve another host credential. Continue to create AWS, cloud, OpenCode, T3 Code, and other credentials inside the guest only when needed.

## Claude Code

After Provisioning, run this command from an interactive macOS terminal:

```bash
./enroll claude
```

Proteus runs `claude auth login` inside the guest using its managed Node runtime. Open the generated login URL in your macOS browser and authorize access. If the browser returns a code, paste it into the waiting terminal. This is Claude Code's documented [manual login flow](https://code.claude.com/docs/en/authentication#log-in-to-claude-code) for sessions where the browser cannot reach the local callback server.

Enrollment requires terminal input and output; piping input or redirecting output fails before login starts. It does not need 1Password or a configured GitHub credential source. The selected instance must already be running and provisioned with Claude Code. Enrollment never starts or provisions it. Proteus reports success only after login succeeds and `claude auth status` confirms authentication.

Claude Code owns storage and renewal of the resulting VM-Local Credential. Using the host browser for authorization does not expose its cookies or credential store to the guest. Proteus does not copy a host Claude credential or capture the returned code. The credential persists across VM stops, is removed when the VM is deleted, and must be enrolled again after a rebuild. Run `./enroll claude` again when Claude Code requires a new login.

See [host configuration](./usage.md#host-configuration) to select the GitHub token source, and [VM details](../vm/README.md#isolation-boundary) for the isolation boundary.
