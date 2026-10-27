# Using Proteus

Proteus uses the Lima instance named `proteus`. Normal work returns to the same VM; when it becomes broken or cluttered, replace it from the VM Definition and run Provisioning again.

Run host commands from the repository root. Run the Git identity commands inside a guest shell.

## Requirements

- An Apple silicon Mac
- [Homebrew](https://brew.sh/)
- Lima 2.2 or later
- Ansible
- [1Password CLI](https://developer.1password.com/docs/cli/) for GitHub Credential Enrollment

Install the host tools:

```bash
brew install lima ansible
brew install --cask 1password-cli
```

The host commands check their own prerequisites but do not install or change macOS software.

## Host configuration

Tell Proteus which 1Password fields contain the fine-grained GitHub personal access token and SSH private signing key:

```bash
./configure
```

Both references are required. The prompts show examples such as `op://vault/item/entry` for the token and `op://vault/item/private key` for the signing key. Proteus stores only the references in `${XDG_CONFIG_HOME:-$HOME/.config}/proteus/config`; it treats them as data and does not contact 1Password. Run `./configure` again to accept the current references or replace either one. If you previously configured only a token, run it again to add the signing-key reference.

The `op` command is not needed while configuring the references. It is required later when Credential Enrollment resolves them. Create the signing key and register its public key with GitHub once, following the [credential guide](./credentials.md#github).

`./configure` then asks for the Salesforce login URL used by `./enroll salesforce`. Press Enter to keep the value shown, which is `https://login.salesforce.com` until you save another. Enter your org's My Domain URL, such as `https://example.my.salesforce.com`, if it requires one. The URL must use `https://`, have a host ending in `.salesforce.com`, and have no path, query, or fragment; a trailing slash is removed. An invalid URL fails without changing the saved configuration. Saving these values preserves unrelated configuration; both GitHub references remain required. If no Salesforce login URL is saved, including in configuration written before this prompt existed, enrollment uses `https://login.salesforce.com`.

## Operating workflow

Run these commands from the repository root. Lima owns the VM lifecycle; Provisioning never creates, starts, stops, or deletes a VM.

| Operation | Command |
| --- | --- |
| Create Proteus from the VM Definition | `limactl create --name=proteus ./vm/proteus.yaml` |
| Start Proteus | `limactl start proteus` |
| Apply Provisioning | `./provision` |
| Enroll GitHub access and commit signing | `./enroll github` |
| Authorize Claude Code inside the guest | `./enroll claude` |
| Authorize T3 Connect and install its persistent guest service | `./enroll t3` |
| Authorize the Salesforce Dev Hub User inside the guest | `./enroll salesforce` |
| Authorize Jira and Confluence through Teamwork Graph | `./enroll twg` |
| Open a guest shell | `limactl shell proteus` |
| Stop Proteus | `limactl stop proteus` |
| Delete a stopped Proteus VM | `limactl delete proteus` |

Create, start, and provision the VM before first use. On later days, start it and open a shell. Put repositories under `~/projects` inside the guest.

`./provision` and all `./enroll` commands accept an optional instance name and target `proteus` by default. The selected instance must already exist and be running. Neither command changes its lifecycle state. For example:

```bash
./provision proteus-acceptance-example
./enroll github proteus-acceptance-example
./enroll claude proteus-acceptance-example
./enroll t3 proteus-acceptance-example
./enroll salesforce proteus-acceptance-example
./enroll twg proteus-acceptance-example
```

## Git identity

The Managed Dotfiles Git configuration sets the default Git identity to Carlos del Moral with a GitHub no-reply email. To override it, set Git identity in the guest-local file it includes:

```bash
git config --file ~/.gitconfig.local user.name "Your Name"
git config --file ~/.gitconfig.local user.email "you@example.com"
```

GitHub Credential Enrollment preserves this identity and unrelated preferences while updating the signing settings in the same file.

## Rebuild Proteus

A different Proteus major version, any downgrade, or an older unversioned guest
requires a fresh VM. Provisioning reports accepted and requested versions and
stops before baseline changes; it never performs the rebuild automatically.
The same release and higher minor/patch releases within its major support
repeated Provisioning. See [release compatibility](./provisioning.md#release-compatibility-and-rebuilds),
including how to retry interrupted runs.

Deleting Proteus permanently removes its repositories, uncommitted work, VM-Local Credentials, Host-Injected Credentials, and other guest state.

If T3 was enrolled, deregister the old environment from your T3 Connect account before rebuilding, or afterward if it has already been wiped. Removing it only from a device's connections does not deregister it. Proteus does not automate cloud cleanup. See [T3 Enrollment](./credentials.md#t3-code).

If Salesforce was enrolled, delete scratch orgs you no longer need with `sf org delete scratch`, then revoke the VM's Salesforce CLI access in the Dev Hub User's personal settings under OAuth Connected Apps before deleting the VM. `sf org logout` only removes the guest-local authorization, so no valid production-org token should outlive the VM. See [Salesforce enrollment](./credentials.md#salesforce).

If Teamwork Graph was enrolled, run `twg logout` inside the guest before deletion and check for revocation failures. If it has already been deleted, revoke the TWG grant through your Atlassian account or ask an organization administrator to revoke TWG sessions. See [Teamwork Graph Enrollment](./credentials.md#teamwork-graph).

After preserving anything you need, run:

```bash
limactl stop proteus
limactl delete proteus
limactl create --name=proteus ./vm/proteus.yaml
limactl start proteus
./provision
./enroll github
./enroll claude
./enroll t3
./enroll salesforce
./enroll twg
limactl shell proteus
```

Then clone your repositories and repeat any other Credential Enrollment. This restores the Development Baseline and the selected GitHub token and signing key, not the rest of the deleted VM's contents. Reusing the signing key preserves its existing GitHub registration.

See [Credential Enrollment](./credentials.md) for authentication details and [Provisioning](./provisioning.md) for the Development Baseline.

## Optional AWS access

`./configure` offers an optional complete AWS group; blank answers keep existing values and `false` opts out. Create an IAM Roles Anywhere workload identity with [`./aws-setup`](./aws-setup.md), or reuse an existing one. Enter the emitted summary values into `./configure` prompts; the summary is YAML, while saved host settings are key=value. Then run `./enroll aws [instance-name]` after Provisioning. See [AWS Credential Enrollment](./aws-enrollment.md) for prerequisites, annual replacement, rebuilding, and emergency revocation. The default profile works through background T3 processes without a service restart.
