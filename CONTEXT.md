# Proteus

This context defines the language for Proteus and credential-isolated development.

## Language

**Proteus**:
A named, rebuildable Credential-Isolated Dev VM for personal software development.
_Avoid_: Container, disposable environment

**Rebuildable Dev VM**:
A virtual machine reused during normal development but replaced from its VM Definition and Provisioning when it becomes broken or cluttered. Its development baseline can be restored in minutes without repairing the existing guest.
_Avoid_: Disposable VM, permanent workstation

**Development Baseline**:
The software and non-secret configuration restored by Provisioning. It excludes VM-Local Credentials, project repositories, uncommitted work, caches, command history, and workspace state.
_Avoid_: Backup, workstation snapshot

**Managed Dotfiles**:
The non-secret user configuration included in the Development Baseline. Proteus installs the collection as a whole without managing each application's configuration separately.
_Avoid_: Provisioning preferences, managed paths

**Credential-Isolated Dev VM**:
A Linux virtual machine used for development where GitHub, AWS, and cloud credentials are created and stored inside the guest rather than shared from the macOS host.
_Avoid_: Separate dev computer, credential-scoped dev environment

**VM-Local Credential**:
A credential created, stored, and used inside the Credential-Isolated Dev VM rather than copied from or delegated by the macOS host.
_Avoid_: Shared credential, forwarded credential

**Production AWS Role**:
An AWS role that can change, deploy, delete, or expose production infrastructure or data.
_Avoid_: Prod access, live credentials

**VM Definition**:
The Lima configuration that creates Proteus and establishes its credential-isolation boundary.
_Avoid_: Provisioning, VM configuration

**Provisioning**:
The repeatable application of software and non-secret configuration to Proteus after its VM Definition has been applied.
_Avoid_: Bootstrap, setup script

**Credential Enrollment**:
The interactive creation and authorization of VM-Local Credentials after Provisioning.
_Avoid_: Credential provisioning, credential import
