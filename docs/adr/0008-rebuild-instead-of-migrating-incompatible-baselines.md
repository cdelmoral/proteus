# Rebuild instead of migrating incompatible Development Baselines

Proteus may require rebuilding the Dev VM when a release introduces incompatible changes to its Development Baseline. We do not maintain migrations across that boundary, including migration from the former npm tool installations; compatible releases continue to support repeated Provisioning for updates and baseline repair.

This trades preservation of an existing guest across breaking changes for simpler Provisioning, consistent with Proteus being a Rebuildable Dev VM. Rebuilding requires preserving project work separately and repeating Credential Enrollment; the Development Baseline does not restore those items.

Version Proteus starting at `1.0.0`. Major versions define rebuild boundaries, minor versions add compatible capabilities, and patch versions provide compatible fixes. Repeated Provisioning supports compatible releases within the same major version. These versions identify the Proteus release, rather than freezing independently updated vendor tool releases.

Provisioning must reject an incompatible guest before making changes, reporting the installed and requested releases and explaining that a rebuild is required. It must never rebuild or delete the VM automatically. Previously provisioned guests without a recorded release require rebuilding; fresh guests may receive the initial versioned release.

Provisioning supports repeating the same release and upgrading within the same major version. It refuses downgrades, including within a major version; using an older release requires a fresh VM. This avoids maintaining rollback behavior alongside the forward Provisioning path.

Keep the release version in a repository `VERSION` file and publish releases deliberately with Git tags such as `v1.0.0`; ordinary commits do not each require a new release. Automated release publishing is not required. Apply this policy to the standalone tool changes in PR #57, removing npm migration support and making `1.0.0` the first versioned baseline.

Record the accepted release before applying baseline changes, so interrupted runs can retry that release without treating the guest as an unversioned older installation. The record identifies the accepted release, not successful completion; after a failed upgrade, older releases remain disallowed.
