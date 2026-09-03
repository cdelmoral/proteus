# Proteus

This context defines the language for Proteus and credential-isolated development.

## Language

**Proteus**:
A persistent, general-purpose Credential-Isolated Dev VM for personal software development.
_Avoid_: Container

**Credential-Isolated Dev VM**:
A Linux virtual machine used for development where GitHub, AWS, and cloud credentials are created and stored inside the guest rather than shared from the macOS host.
_Avoid_: Separate dev computer, credential-scoped dev environment

**VM-Local Credential**:
A credential created, stored, and used inside the Credential-Isolated Dev VM rather than copied from or delegated by the macOS host.
_Avoid_: Shared credential, forwarded credential

**Production AWS Role**:
An AWS role that can change, deploy, delete, or expose production infrastructure or data.
_Avoid_: Prod access, live credentials
