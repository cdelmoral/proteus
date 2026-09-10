# Use Ansible for Provisioning

Proteus uses an Ansible playbook run explicitly from macOS over Lima's generated SSH configuration so that Provisioning is repeatable without weakening the credential-isolation boundary. The playbook manages software and non-secret configuration, while Credential Enrollment remains interactive and VM-local. It replaces the shell implementation instead of coexisting with it because two Provisioning paths would drift.
