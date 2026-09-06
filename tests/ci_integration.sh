#!/usr/bin/env bash
set -euo pipefail

repository_root="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"
readonly repository_root
readonly ci_user="proteus-ci"
work_directory="$(mktemp -d)"
readonly work_directory
readonly private_key="${work_directory}/id_ed25519"
readonly second_run_output="${work_directory}/second-run.log"
readonly sudoers_file="${work_directory}/sudoers"
readonly playbook="${repository_root}/provisioning/playbook.yml"
readonly -a ssh_options=(
  -o BatchMode=yes
  -o StrictHostKeyChecking=no
  -o UserKnownHostsFile=/dev/null
  -o LogLevel=ERROR
)
readonly -a playbook_arguments=(
  --inventory "127.0.0.1,"
  --user "$ci_user"
  --private-key "$private_key"
  --ssh-common-args="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR"
  "$playbook"
)
trap 'rm -rf "$work_directory"' EXIT

if [[ "$(uname -s)" != Linux || "$(uname -m)" != aarch64 ]]; then
  printf 'CI integration requires Linux on aarch64.\n' >&2
  exit 1
fi

if id "$ci_user" >/dev/null 2>&1; then
  printf 'CI test user already exists: %s\n' "$ci_user" >&2
  exit 1
fi

sudo useradd --create-home --shell /bin/bash "$ci_user"
printf '%s ALL=(ALL) NOPASSWD:ALL\n' "$ci_user" >"$sudoers_file"
sudo install -o root -g root -m 0440 "$sudoers_file" "/etc/sudoers.d/$ci_user"

ssh-keygen -q -t ed25519 -N '' -f "$private_key"
sudo install -d -o "$ci_user" -g "$ci_user" -m 0700 "/home/$ci_user/.ssh"
sudo install -o "$ci_user" -g "$ci_user" -m 0600 "${private_key}.pub" "/home/$ci_user/.ssh/authorized_keys"
sudo systemctl enable --now ssh

ssh_ready=false
for _ in {1..10}; do
  if ssh "${ssh_options[@]}" -i "$private_key" "$ci_user@127.0.0.1" true; then
    ssh_ready=true
    break
  fi
  sleep 1
done

if [[ "$ssh_ready" != true ]]; then
  printf 'Loopback SSH did not become ready.\n' >&2
  exit 1
fi

ANSIBLE_FORCE_COLOR=0 ansible-playbook "${playbook_arguments[@]}"
ANSIBLE_FORCE_COLOR=0 ansible-playbook "${playbook_arguments[@]}" | tee "$second_run_output"
"${repository_root}/tests/assert_converged.sh" "$second_run_output"
