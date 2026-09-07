#!/usr/bin/env bash
set -euo pipefail

repository_root="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"
readonly repository_root
test_directory="$(mktemp -d)"
readonly test_directory
readonly controller_home="${test_directory}/controller-home"
readonly managed_home="${test_directory}/managed-home"
readonly fixture_directory="${test_directory}/fixtures"
readonly mise_fixture="${fixture_directory}/mise"
readonly pnpm_fixture="${fixture_directory}/pnpm.tar.gz"
readonly playbook="${test_directory}/playbook.yml"
trap 'rm -rf "$test_directory"' EXIT

mkdir -p \
  "$controller_home" \
  "$managed_home/.local/share/proteus/pnpm/12.3.4/dist" \
  "${fixture_directory}/pnpm/dist"

cat >"$mise_fixture" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

managed_home="$(CDPATH='' cd -- "$(dirname -- "$0")/../../../../.." && pwd)"
readonly managed_home
readonly managed_config_home="${managed_home}/.config"
readonly mise_config_home="${XDG_CONFIG_HOME:-${HOME}/.config}"

if [[ "$HOME" != "$managed_home" || "$mise_config_home" != "$managed_config_home" ]]; then
  printf 'mise ERROR failed create_dir_all: %s/mise\n' "$mise_config_home" >&2
  exit 1
fi

case "$1" in
  config)
    exit 1
    ;;
  where)
    [[ -e "$mise_config_home/mise/config.toml" ]] || exit 1
    printf '%s\n' "$HOME/.local/share/mise/installs/node/24.20.0"
    ;;
  use)
    mkdir -p \
      "$mise_config_home/mise" \
      "$HOME/.local/share/mise/installs/node/24.20.0/bin" \
      "$HOME/.local/share/mise/installs/node/24.20.0/lib/node_modules/corepack"
    : >"$mise_config_home/mise/config.toml"
    : >"$HOME/.local/share/mise/installs/node/24.20.0/bin/corepack"
    ;;
  *)
    exit 2
    ;;
esac
EOF
chmod +x "$mise_fixture"

printf '#!/usr/bin/env sh\nprintf "12.3.4\\n"\n' >"${fixture_directory}/pnpm/pnpm"
chmod +x "${fixture_directory}/pnpm/pnpm"
cp "${fixture_directory}/pnpm/pnpm" \
  "$managed_home/.local/share/proteus/pnpm/12.3.4/pnpm"
tar -czf "$pnpm_fixture" -C "${fixture_directory}/pnpm" .

cat >"$playbook" <<EOF
---
- name: Verify mise uses the managed user's home
  hosts: localhost
  connection: local
  gather_facts: false
  vars:
    ansible_user_dir: "$managed_home"
    mise_version: test
    mise_install_dir: "{{ ansible_user_dir }}/.local/share/proteus/mise/{{ mise_version }}"
    mise_binary: "{{ mise_install_dir }}/mise"
    mise_download_url: "file://$mise_fixture"
    mise_checksum: ""
    node_version: "24.20.0"
    pnpm_version: "12.3.4"
    pnpm_download_url: "file://$pnpm_fixture"
    pnpm_checksum: ""
    pnpm_archive: "{{ ansible_user_dir }}/.cache/proteus/pnpm.tar.gz"
    pnpm_install_dir: "{{ ansible_user_dir }}/.local/share/proteus/pnpm/{{ pnpm_version }}"
  tasks:
    - name: Exercise the production JavaScript tasks
      ansible.builtin.import_tasks: "$repository_root/provisioning/tasks/javascript.yml"
EOF

playbook_output="${test_directory}/playbook.log"
if ! HOME="$controller_home" XDG_CONFIG_HOME="$controller_home/.config" \
  ANSIBLE_FORCE_COLOR=0 \
  ansible-playbook --inventory localhost, "$playbook" >"$playbook_output" 2>&1; then
  printf '%s\n' "$(<"$playbook_output")" >&2
  exit 1
fi

[[ -e "$managed_home/.config/mise/config.toml" ]]
[[ ! -e "$controller_home/.config/mise" ]]

printf 'ok - mise uses the managed user home\n'
