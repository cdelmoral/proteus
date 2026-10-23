"""Host issuance and conservative, resumable AWS resource creation.

All external diagnostics are captured: CLI errors may contain private material.
No secret values are passed in arguments or environment variables.
"""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
from urllib.parse import unquote


class SetupError(Exception):
    pass


def run(arguments, *, data=None, environment=None, description=None):
    result = subprocess.run(
        [str(value) for value in arguments], input=data, text=True,
        capture_output=True, env=environment,
    )
    if result.returncode:
        # Never echo subprocess output, arguments, or exception details.
        raise SetupError(f"{description or Path(arguments[0]).name} failed; setup is incomplete. Check authentication, permissions and selected resources, then retry with the same references.")
    return result.stdout


def json_run(arguments, **kwargs):
    if arguments[:2] == ["op", "item"]:
        kwargs["description"] = "1Password item " + arguments[2]
    try:
        return json.loads(run(arguments, **kwargs))
    except (ValueError, TypeError):
        raise SetupError("External command returned invalid JSON; setup is incomplete.") from None


def ask(message):
    try:
        value = input(message).strip()
    except EOFError:
        raise SetupError("Input interrupted; setup is incomplete.") from None
    if not value or any(ord(character) < 32 for character in value):
        raise SetupError("A nonempty answer without control characters is required.")
    return value


def approve(message):
    if ask(message + " [yes/no]: ").lower() != "yes":
        raise SetupError("Declined; setup is incomplete. Existing credentials and resources were preserved.")


class Item:
    """One explicitly selected item, with fixed, unsectioned credential fields."""
    def __init__(self, reference):
        match = re.fullmatch(r"op://([^/]+)/([^/]+)/certificate", reference)
        if not match:
            raise SetupError("Use op://vault/item/certificate (no section); private key is a sibling field.")
        self.vault, self.name = match.groups()
        if self.vault.startswith("-") or self.name.startswith("-"):
            raise SetupError("Vault and item identifiers cannot start with '-'.")
        self.reference = reference
        items = json_run(["op", "item", "list", "--vault", self.vault, "--format", "json", "--include-archive"])
        matches = [item for item in items if self.name in (item["id"], item["title"])]
        if len(matches) > 1:
            raise SetupError("Ambiguous 1Password item; select its unique item ID.")
        self.document = None
        if matches and matches[0].get("state", "ACTIVE") != "ACTIVE":
            raise SetupError("Selected item is archived; restore it before retrying. No replacement was created.")
        if matches:
            self.document = json_run(["op", "item", "get", matches[0]["id"], "--vault", self.vault, "--format", "json", "--reveal"])

        if self.document and self.document.get("category") != "SECURE_NOTE":
            raise SetupError("Select a dedicated Secure Note item; other item categories are never modified.")

    def field(self, label):
        fields = [field for field in (self.document or {}).get("fields", [])
                  if field.get("label") == label and not field.get("section")]
        if len(fields) > 1:
            raise SetupError("Duplicate credential fields in selected item; refusing to overwrite.")
        return fields[0] if fields else None

    def value(self, label):
        field = self.field(label)
        return field.get("value", "") if field is not None else ""

    def same_item(self, other):
        if (self.vault, self.name) == (other.vault, other.name):
            return True
        return bool(self.document and other.document
                    and self.canonical_reference() == other.canonical_reference())

    def store(self, certificate, key, identity):
        document = self.document or {"title": self.name, "category": "SECURE_NOTE", "fields": []}
        fields = document["fields"]
        for label, value, kind in (("certificate", certificate, "STRING"),
                                   ("private key", key, "CONCEALED"),
                                   ("proteus identity", identity, "STRING")):
            existing = self.field(label)
            if existing is not None:
                existing["value"] = value
                existing["type"] = kind
            else:
                fields.append({"id": label.replace(" ", "_"), "label": label, "type": kind, "value": value})
        if self.document:
            command = ["op", "item", "edit", self.document["id"], "--vault", self.vault, "--format", "json"]
        else:
            command = ["op", "item", "create", "--vault", self.vault, "--format", "json", "-"]
        # Item JSON is consumed from stdin by both create and edit.
        self.document = json_run(command, data=json.dumps(document))
        # Read back both fields before declaring storage complete.
        saved = json_run(["op", "item", "get", self.document["id"], "--vault", self.vault, "--format", "json", "--reveal"])
        self.document = saved
        if self.value("certificate") != certificate or self.value("private key") != key:
            raise SetupError("1Password read-back did not match the issued pair; setup is incomplete.")

    def canonical_reference(self):
        return f"op://{self.document['vault']['id']}/{self.document['id']}/certificate"


def write(path, value):
    path.write_text(value)
    path.chmod(0o600)


def openssl(*arguments):
    return run(["openssl", *arguments], description="OpenSSL " + arguments[0])


def validate_pair(directory, prefix, certificate, key, cn, ca=False):
    cert_path, key_path = directory / f"{prefix}.pem", directory / f"{prefix}.key"
    write(cert_path, certificate)
    write(key_path, key)
    public_certificate = openssl("x509", "-in", cert_path, "-pubkey", "-noout")
    public_key = openssl("pkey", "-in", key_path, "-passin", "pass:", "-pubout")
    if public_certificate != public_key:
        raise SetupError("Stored certificate and private key do not match; refusing replacement.")
    subject = openssl("x509", "-in", cert_path, "-subject", "-noout", "-nameopt", "RFC2253").strip()
    if subject != f"subject=CN={cn}":
        raise SetupError("Stored certificate has an unexpected workload identity.")
    text = openssl("x509", "-in", cert_path, "-text", "-noout")
    if ("CA:TRUE" if ca else "CA:FALSE") not in text:
        raise SetupError("Stored certificate has incorrect basic constraints.")
    openssl("x509", "-in", cert_path, "-checkend", "0", "-noout")
    openssl("verify", "-CAfile", cert_path if ca else directory / "ca.pem", cert_path)
    return cert_path, key_path


def issue(directory, cn, ca=False):
    prefix = "ca" if ca else "workload"
    key, cert = directory / f"{prefix}.key", directory / f"{prefix}.pem"
    openssl("genpkey", "-algorithm", "EC", "-pkeyopt", "ec_paramgen_curve:P-256", "-out", key)
    extension = directory / f"{prefix}.cnf"
    write(extension, "[req]\ndistinguished_name=dn\n[dn]\n[extensions]\n"
          + ("basicConstraints=critical,CA:TRUE,pathlen:0\nkeyUsage=critical,keyCertSign,cRLSign\n"
             if ca else "basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\n")
          + "subjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid:always\n")
    if ca:
        openssl("req", "-new", "-x509", "-key", key, "-sha256", "-days", "3650",
                "-subj", f"/CN={cn}", "-config", extension, "-extensions", "extensions", "-out", cert)
    else:
        csr = directory / "workload.csr"
        openssl("req", "-new", "-key", key, "-subj", f"/CN={cn}", "-out", csr)
        openssl("x509", "-req", "-in", csr, "-CA", directory / "ca.pem", "-CAkey", directory / "ca.key",
                "-set_serial", "0x" + secrets.token_hex(16), "-days", "365", "-sha256",
                "-extfile", extension, "-extensions", "extensions", "-out", cert)
    return cert.read_text(), key.read_text()


class AWS:
    def __init__(self, arguments):
        self.arguments = arguments
        # Explicit profile selects the administrative identity, not ambient keys.
        self.environment = {key: value for key, value in os.environ.items()
                            if not key.startswith("AWS_") or key in ("AWS_CONFIG_FILE", "AWS_SHARED_CREDENTIALS_FILE")}
        self.environment.update(AWS_PAGER="", AWS_CLI_AUTO_PROMPT="off")

    def call(self, service, operation, **values):
        command = ["aws", "--profile", self.arguments.admin_profile, "--region", self.arguments.region,
                   "--output", "json", service, operation]
        for key, value in values.items():
            command.append("--" + key.replace("_", "-"))
            if value is not True:
                command.append(value if isinstance(value, str) else json.dumps(value))
        # IAM attachment documents no output, even with --output json.
        execute = run if (service, operation) == ("iam", "attach-role-policy") else json_run
        return execute(command, environment=self.environment, description=f"AWS {service} {operation}")

    def named(self, service, operation, collection, name):
        matches = [item for item in self.call(service, operation)[collection]
                   if item.get("name", item.get("RoleName")) == name]
        if len(matches) > 1:
            raise SetupError("Multiple AWS resources share the selected name; refusing adoption.")
        return matches[0] if matches else None


def configure_resources(aws, args, ca_certificate):
    source = {"sourceType": "CERTIFICATE_BUNDLE", "sourceData": {"x509CertificateData": ca_certificate}}
    anchor = aws.named("rolesanywhere", "list-trust-anchors", "trustAnchors", args.name)
    if anchor:
        if anchor["source"] != source or not anchor["enabled"]:
            raise SetupError("Existing trust anchor differs or is disabled; refusing replacement.")
    else:
        anchor = aws.call("rolesanywhere", "create-trust-anchor", name=args.name, source=source, enabled=True)["trustAnchor"]
    anchor_arn = anchor["trustAnchorArn"]
    if not anchor_arn.startswith(f"arn:aws:rolesanywhere:{args.region}:{args.account_id}:trust-anchor/"):
        raise SetupError("Unexpected trust anchor ARN.")
    trust = {"Version": "2012-10-17", "Statement": [{
        "Effect": "Allow", "Principal": {"Service": "rolesanywhere.amazonaws.com"},
        "Action": ["sts:AssumeRole", "sts:SetSourceIdentity", "sts:TagSession"],
        "Condition": {"ArnEquals": {"aws:SourceArn": anchor_arn}, "StringEquals": {
            "aws:SourceAccount": args.account_id, "aws:PrincipalTag/x509Subject/CN": args.name}},
    }]}
    role_arn = f"arn:aws:iam::{args.account_id}:role/{args.name}"
    role = aws.named("iam", "list-roles", "Roles", args.name)
    if role:
        policy = role["AssumeRolePolicyDocument"]
        if isinstance(policy, str):
            policy = json.loads(unquote(policy))
        if role["Arn"] != role_arn or policy != trust:
            raise SetupError("Existing role trust differs; refusing to modify an unrelated role.")
    else:
        aws.call("iam", "create-role", role_name=args.name, assume_role_policy_document=trust)
    # Idempotent attachment also repairs a failure immediately after role creation.
    aws.call("iam", "attach-role-policy", role_name=args.name,
             policy_arn="arn:aws:iam::aws:policy/AdministratorAccess")
    profile = aws.named("rolesanywhere", "list-profiles", "profiles", args.name)
    if profile:
        profile = aws.call("rolesanywhere", "get-profile", profile_id=profile["profileId"])["profile"]
        if (profile["roleArns"] != [role_arn] or not profile["enabled"]
                or profile.get("sessionPolicy") or profile.get("managedPolicyArns")
                or profile.get("requireInstanceProperties") or profile.get("acceptRoleSessionName")):
            raise SetupError("Existing Roles Anywhere profile differs; refusing replacement.")
    else:
        profile = aws.call("rolesanywhere", "create-profile", name=args.name, role_arns=[role_arn],
                           duration_seconds="3600", enabled=True)["profile"]
    profile_arn = profile["profileArn"]
    if not profile_arn.startswith(f"arn:aws:rolesanywhere:{args.region}:{args.account_id}:profile/"):
        raise SetupError("Unexpected Roles Anywhere profile ARN.")
    return role_arn, anchor_arn, profile_arn


def verify_identity(directory, args, role, anchor, profile):
    helper = str(Path(shutil.which("aws_signing_helper")).resolve())
    command = [helper, "credential-process", "--certificate", str(directory / "workload.pem"),
               "--private-key", str(directory / "workload.key"), "--trust-anchor-arn", anchor,
               "--profile-arn", profile, "--role-arn", role, "--region", args.region]
    config = directory / "aws-config"
    write(config, f"[default]\nregion = {args.region}\ncredential_process = {shlex.join(command)}\n")
    credentials = directory / "aws-credentials"
    write(credentials, "")
    environment = {key: value for key, value in os.environ.items() if not key.startswith("AWS_")}
    environment.update(AWS_CONFIG_FILE=str(config), AWS_SHARED_CREDENTIALS_FILE=str(credentials),
                       AWS_EC2_METADATA_DISABLED="true", AWS_PAGER="", AWS_CLI_AUTO_PROMPT="off")
    identity = json_run(["aws", "--region", args.region, "--output", "json", "sts", "get-caller-identity"],
                        environment=environment)
    expected = f"arn:aws:sts::{args.account_id}:assumed-role/{args.name}/"
    if identity.get("Account") != args.account_id or not identity.get("Arn", "").startswith(expected):
        raise SetupError("Workload identity verification returned the wrong account or role; setup is incomplete.")


def setup(args):
    aws = AWS(args)
    if aws.call("sts", "get-caller-identity").get("Account") != args.account_id:
        raise SetupError("Administrative identity account mismatch; no AWS changes made.")
    approve("Confirm external organization controls isolate this development account from production and other accounts")
    workload = Item(ask("Workload certificate reference (op://vault/item/certificate): "))
    ca = Item(ask("Separate protected CA certificate reference (op://vault/item/certificate): "))
    if workload.same_item(ca):
        raise SetupError("CA and workload must be separate 1Password items.")
    identity = f"{args.account_id}/{args.region}/{args.name}"
    for item in (ca, workload):
        if item.document and item.value("proteus identity") not in ("", identity):
            raise SetupError("Selected item belongs to another Proteus identity.")
    existing_workload = bool(workload.value("certificate") or workload.value("private key"))
    if not existing_workload:
        approve(("Update" if workload.document else "Create") + " selected workload item with a coherent certificate/private-key pair")
    if not ca.document and existing_workload:
        raise SetupError("Selected CA item is missing for an existing workload; restore its backup rather than creating a new CA.")
    if not ca.document:
        approve("Create selected protected CA item; its signing key must remain host-only")
    elif not ca.value("certificate") or not ca.value("private key"):
        raise SetupError("Existing CA item is incomplete; restore its backup. A retry never replaces the CA.")
    # The context manager removes material on failure, success and handled signals.
    with tempfile.TemporaryDirectory(prefix="proteus-aws-") as temporary:
        directory = Path(temporary)
        if not ca.document:
            certificate, key = issue(directory, args.name + "-ca", ca=True)
            ca.store(certificate, key, identity)
        validate_pair(directory, "ca", ca.value("certificate"), ca.value("private key"), args.name + "-ca", ca=True)
        if existing_workload:
            if not workload.value("certificate") or not workload.value("private key"):
                raise SetupError("Existing workload pair is incomplete; restore it or select a new empty item. Renewal is separate.")
            certificate, key = workload.value("certificate"), workload.value("private key")
            print("Reusing the existing workload pair; no certificate rotation requested.")
        else:
            # Ensure the CA will remain valid for the entire new certificate lifetime.
            openssl("x509", "-in", directory / "ca.pem", "-checkend", str(365 * 86400), "-noout")
            certificate, key = issue(directory, args.name)
        validate_pair(directory, "workload", certificate, key, args.name)
        if not existing_workload:
            # Store before AWS changes so a retry reuses exactly this identity.
            workload.store(certificate, key, identity)
        role, anchor, profile = configure_resources(aws, args, ca.value("certificate"))
        verify_identity(directory, args, role, anchor, profile)
    print("Verified workload AWS account and role. Setup complete; configure and enroll AWS separately.")
    settings = {"proteus_aws_enabled": True, "proteus_aws_account_id": args.account_id,
                "proteus_aws_role_arn": role, "proteus_aws_region": args.region,
                "proteus_aws_trust_anchor_arn": anchor, "proteus_aws_profile_arn": profile,
                "proteus_aws_certificate_ref": workload.canonical_reference(),
                "proteus_aws_private_key_ref": workload.canonical_reference().rsplit("/", 1)[0] + "/private key"}
    for key, value in settings.items():
        print(f"{key}: " + ("true" if value is True else json.dumps(value)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", required=True, help="intended isolated development account")
    parser.add_argument("--admin-profile", required=True, help="explicit authenticated host AWS CLI profile")
    parser.add_argument("--region", required=True)
    parser.add_argument("--name", default="proteus", help="dedicated resource name and certificate CN (default: proteus)")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if not re.fullmatch(r"[0-9]{12}", args.account_id):
            raise SetupError("Account ID must contain exactly 12 digits.")
        if not re.fullmatch(r"[a-z]{2}-[a-z]+-[0-9]+", args.region):
            raise SetupError("Use a standard AWS commercial region; other partitions are not supported.")
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,48}", args.name) or args.name.startswith("aws"):
            raise SetupError("Name must have 1–48 letters, numbers, underscores or hyphens, without the reserved aws prefix.")
        if not args.admin_profile or any(ord(char) < 32 for char in args.admin_profile):
            raise SetupError("Select a nonempty administrative profile without control characters.")
        for command in ("aws", "op", "openssl", "aws_signing_helper"):
            if not shutil.which(command):
                raise SetupError(f"Required host command is missing: {command}.")
        def interrupted(_signum, _frame):
            raise SetupError("Interrupted; setup is incomplete. Retry with the same references.")
        signal.signal(signal.SIGTERM, interrupted)
        signal.signal(signal.SIGINT, interrupted)
        setup(args)
        return 0
    except (SetupError, OSError, KeyError, TypeError, ValueError) as error:
        message = str(error) if isinstance(error, SetupError) else "Host operation failed; setup is incomplete. Retry with the same references."
        print(f"aws-setup: {message}", file=sys.stderr)
        return 1
