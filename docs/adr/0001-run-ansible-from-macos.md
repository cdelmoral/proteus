# Run Ansible from macOS over Lima SSH

Ansible runs explicitly from macOS through Lima-generated SSH configuration because Lima owns the guest's dynamic connection details and host administration does not require access to guest credentials. Credential Enrollment remains inside Proteus. We reject host filesystem mounts, SSH key import, and SSH agent forwarding because each would expose macOS credentials to the VM and break the Credential-Isolated Dev VM boundary.

ADR 0002 supersedes only the statement that Credential Enrollment always remains inside Proteus. The other isolation decisions remain in effect.
