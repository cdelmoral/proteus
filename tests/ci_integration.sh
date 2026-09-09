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
readonly project_version_test="${repository_root}/tests/pnpm_project_version.sh"
readonly unmanaged_shell_sentinel=".proteus-smoke-ran-unmanaged-shell"
readonly unmanaged_opencode_file=".config/opencode/unmanaged-note"
readonly unmanaged_nvim_file=".config/nvim/unmanaged.lua"
readonly opencode_auth_file=".local/share/opencode/auth.json"
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
unmanaged_corepack_created=false

cleanup() {
  rm -rf "$work_directory"
  if [[ "$unmanaged_corepack_created" == true ]]; then
    sudo rm -f /usr/local/bin/corepack
  fi
}

trap cleanup EXIT

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

if [[ ! -e /usr/local/bin/corepack && ! -L /usr/local/bin/corepack ]]; then
  printf '%s\n' '#!/usr/bin/env sh' 'printf "unmanaged Corepack\n"' \
    >"${work_directory}/corepack"
  sudo install -o root -g root -m 0755 "${work_directory}/corepack" /usr/local/bin/corepack
  unmanaged_corepack_created=true
fi

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

ssh "${ssh_options[@]}" -i "$private_key" "$ci_user@127.0.0.1" \
  "mkdir -p \"\$HOME/.config/opencode\" \"\$HOME/.config/nvim\" \"\$HOME/.local/share/opencode\" &&
  printf '%s\n' 'preserve OpenCode sibling' >\"\$HOME/$unmanaged_opencode_file\" &&
  printf '%s\n' 'return {}' >\"\$HOME/$unmanaged_nvim_file\" &&
  printf '%s\n' '{\"test-provider\":\"preserve-auth-state\"}' >\"\$HOME/$opencode_auth_file\""

ANSIBLE_FORCE_COLOR=0 ansible-playbook "${playbook_arguments[@]}"
ssh "${ssh_options[@]}" -i "$private_key" "$ci_user@127.0.0.1" \
  /usr/bin/bash -s <"$project_version_test"
ssh "${ssh_options[@]}" -i "$private_key" "$ci_user@127.0.0.1" \
  "printf '%s\\n' 'touch \"\$HOME/$unmanaged_shell_sentinel\"' >>\"\$HOME/.bashrc\""
ANSIBLE_FORCE_COLOR=0 ansible-playbook "${playbook_arguments[@]}" | tee "$second_run_output"
"${repository_root}/tests/assert_converged.sh" "$second_run_output"
ssh "${ssh_options[@]}" -i "$private_key" "$ci_user@127.0.0.1" \
  "grep -Fqx 'touch \"\$HOME/$unmanaged_shell_sentinel\"' \"\$HOME/.bashrc\" &&
  test ! -e \"\$HOME/$unmanaged_shell_sentinel\" &&
  grep -Fqx 'preserve OpenCode sibling' \"\$HOME/$unmanaged_opencode_file\" &&
  grep -Fqx 'return {}' \"\$HOME/$unmanaged_nvim_file\" &&
  grep -Fqx '{\"test-provider\":\"preserve-auth-state\"}' \"\$HOME/$opencode_auth_file\" &&
  test -e /usr/local/bin/corepack"
