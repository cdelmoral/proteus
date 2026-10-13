# Allow a Dev Hub User credential from the production Salesforce org

Proteus may hold an OAuth credential for a Dev Hub User so scratch orgs can be created and used inside the VM. The Dev Hub is enabled only in the production Salesforce org, so this is a deliberate exception to treating production access as outside the security model. It is acceptable because the Dev Hub User is a dedicated user whose minimal permissions allow only scratch org management; it does not permit any other production Salesforce identity, and it does not relax the rule against a Production AWS Role.

The credential is a VM-Local Credential. Enrollment authorizes it in the macOS browser, whose OAuth redirect reaches Salesforce CLI's callback server in the guest through a localhost port forward for port 1717; no Salesforce token is stored on macOS or in 1Password.
