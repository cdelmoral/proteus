# Activate the T3 service during explicit enrollment

T3 Enrollment authorizes and links Proteus and establishes a persistent background service, while Provisioning installs only the CLI and Provider Credential Enrollment remains separate. This gives explicit enrollment a predictable outcome without making the Development Baseline remotely accessible or letting Provisioning interrupt running work. Service runtime upgrades and disruptive repairs remain explicit operations; enrollment preserves completed authorization on failure and reports incomplete setup when activation requires a restart.
