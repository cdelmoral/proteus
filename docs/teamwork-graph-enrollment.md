# Teamwork Graph enrollment design

Agreed through the design interview on 2026-10-17 and implemented through Provisioning and `./enroll twg`. See the [operating guide](./credentials.md#teamwork-graph) for enrollment, recovery, and revocation.

## Agreed requirements

- Provision Teamwork Graph CLI (`twg`) for agents inside Proteus.
- Use the owner's personal Atlassian identity rather than a dedicated agent account.
- Support reading and searching Jira and Confluence.
- Support Jira issue creation, updates, and comments.
- Support Confluence content creation and editing.
- Keep Provisioning separate from Teamwork Graph Enrollment, following Proteus's existing credential boundary.
- Treat the supported operations as required workflows, using existing Atlassian permissions rather than implementing a custom command restriction layer.
- Enroll one default Jira/Confluence Cloud site initially. Tasks select their project or space; enrollment imposes no additional project/space restriction.
- Authorize in the VM through TWG's verification URL opened in the owner's macOS browser. TWG owns storage and refresh of the resulting VM-Local Credential in its default file store.

## Provisioning and agent access

Provisioning installs the latest released Linux ARM64 CLI and Atlassian's official TWG skills at user scope, including the universal skill directory and the supported locations for installed agents. Repeating Provisioning updates the CLI and skills while preserving credentials. The CLI must be available to background agents without relying on interactive shell startup.

Provisioning does not authenticate. Enrollment remains an explicit command from macOS against an already running, provisioned guest, following the existing enrollment interface and VM lifecycle rules.

Agents default to basic Jira and Confluence operations. Enriched operations that consume Rovo credits require an explicit user request. This is agent guidance rather than a technical restriction on the OAuth credential.

Jira transitions, deletion, and administration are not required workflows. This does not imply the selected OAuth credential technically excludes those operations.

## Enrollment and credential lifecycle

Enrollment uses TWG's interactive OAuth flow with a controlling terminal. The owner opens the printed verification URL on macOS and authorizes their personal Atlassian identity. Site selection happens through TWG's enrollment flow, with one default site saved by TWG. Credentials remain in TWG's default file store inside the guest; host Atlassian credentials are not copied.

Enrollment enables TWG's background upkeep helper, including the systemd user-session prerequisites required for refresh after logout. Healthy existing authorization is preserved on repeated enrollment; an expired or revoked authorization can be enrolled again. Provisioning preserves enrolled credentials.

Credentials persist across VM stops. A rebuilt VM requires fresh enrollment. Document TWG logout and remote revocation before VM deletion, including recovery if the VM has already been deleted; do not treat deleting local files as proof of remote revocation.

## Minimal completion check

Use TWG's native basic authentication/connectivity check (`twg doctor --basic`) as the completion signal. Do not add Jira/Confluence read probes, test writes, a background-process test, or elaborate service-health validation to enrollment. Enabling upkeep must still report command failures normally.

Successful enrollment establishes TWG's reported authentication status; it does not certify every project, space, or write permission. Any later write smoke test uses a test issue/page explicitly selected by the owner and is separate from enrollment.

## Verified constraints

Personal TWG authentication uses OAuth 2.1, saves credentials locally, and reuses the account's existing permissions. Access tokens last eight hours and refresh as needed; refresh tokens expire after 30 days without use. TWG provides an upkeep helper for refresh outside an agent sandbox. Linux's experimental encrypted store requires a separately supplied environment key; the default profile store is file based. See [Atlassian's authentication documentation](https://developer.atlassian.com/cloud/twg-cli/getting-started/how-authentication-works/) (checked 2026-10-17).

The VM is ARM64. Although the installation overview lists only Linux x64, the [official installer](https://teamwork-graph.atlassian.com/cli/install) selects a Linux ARM64 binary, and the [v1.3.6 checksum manifest](https://teamwork-graph.atlassian.com/cli/SHA256SUMS-v1.3.6) includes it. The real Provisioning tasks were exercised in an isolated temporary home on ARM64 Linux, including checksum verification and official skill installation. Real account authorization and macOS-to-Lima enrollment still require manual acceptance.

TWG OAuth permission controls are configured in Atlassian Administration for the organization and enforced by Atlassian. These are distinct from a local list of intended agent workflows. See [permission configuration](https://developer.atlassian.com/cloud/twg-cli/getting-started/configure-permissions/).

On Linux, TWG upkeep uses a systemd user timer with an active user D-Bus session. It refreshes credentials and checks for upgrades but does not install upgrades. The OAuth flow documents a verification URL and short code, with no localhost callback requirement. See [OAuth configuration](https://developer.atlassian.com/cloud/twg-cli/getting-started/configure-oauth/).

TWG's official [agent skills](https://developer.atlassian.com/cloud/twg-cli/agents/skills/) install to `~/.agents/skills` and detected agent-specific directories, including Claude Code. [Enriched calls](https://developer.atlassian.com/cloud/twg-cli/faq/) consume Rovo credits; basic product reads are included with the plan and writes are free.
