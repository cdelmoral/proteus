#!/usr/bin/env bash
set -euo pipefail

repository_root="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"
readonly repository_root
readonly variables="${repository_root}/provisioning/group_vars/all.yml"
readonly tasks="${repository_root}/provisioning/tasks/javascript.yml"
readonly smoke_tasks="${repository_root}/provisioning/tasks/javascript_smoke.yml"
readonly shell_tasks="${repository_root}/provisioning/tasks/javascript_shell.yml"
readonly shell_smoke_tasks="${repository_root}/provisioning/tasks/javascript_shell_smoke.yml"
readonly project_version_test="${repository_root}/tests/pnpm_project_version.sh"
readonly ci_integration="${repository_root}/tests/ci_integration.sh"
readonly playbook="${repository_root}/provisioning/playbook.yml"

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

assert_contains() {
  local file="$1"
  local expected="$2"

  [[ "$(<"$file")" == *"$expected"* ]] || fail "expected $file to contain: $expected"
}

assert_not_contains() {
  local file="$1"
  local unexpected="$2"

  [[ "$(<"$file")" != *"$unexpected"* ]] || fail "expected $file not to contain: $unexpected"
}

assert_contains "$variables" 'mise_version: "2026.9.1"'
assert_contains "$variables" 'sha256:0ef0a778eaa8599f3e90a8a0979c9fc3f79922cafb5fa6d39f366d974da33bba'
assert_contains "$variables" 'node_version: "24.20.0"'
assert_contains "$variables" 'pnpm_version: "12.3.4"'
assert_contains "$variables" 'sha256:95e71a2a30bbc0b77511f95cf096779068dcad6ffcbbfdf0cd4dde9de2b2b97c'
assert_contains "$tasks" 'selected_node_version.stdout | trim != node_version'
assert_contains "$tasks" 'or installed_node.rc != 0'
assert_contains "$tasks" 'node@{{ node_version }}'
assert_contains "$tasks" '{{ managed_node.stdout | trim }}/bin/corepack'
assert_contains "$tasks" '{{ managed_node.stdout | trim }}/lib/node_modules/corepack'
assert_contains "$smoke_tasks" 'smoke_managed_node.stdout | trim'
assert_contains "$smoke_tasks" '"PATH": (smoke_managed_node.stdout | trim) ~ "/bin:/usr/bin:/bin"'
assert_contains "$shell_tasks" '# {mark} ANSIBLE MANAGED BLOCK: Proteus JavaScript toolchain'
# The assertion checks a literal shell block embedded in Ansible.
# shellcheck disable=SC2016
assert_contains "$shell_tasks" 'export PNPM_HOME="$HOME/.local/share/proteus/pnpm/{{ pnpm_version }}"'
assert_contains "$playbook" '        - development_tools'
assert_contains "$playbook" '        - shell'
assert_contains "$shell_smoke_tasks" '--norc'
assert_contains "$shell_smoke_tasks" 'source <('
assert_not_contains "$shell_smoke_tasks" '--rcfile'
assert_contains "$project_version_test" '"packageManager": "pnpm@12.3.3"'
assert_contains "$project_version_test" 'command -v corepack'
# This assertion checks a literal shell variable reference in the integration script.
# shellcheck disable=SC2016
assert_contains "$ci_integration" '"$project_version_test"'
assert_not_contains "$tasks" 'node@lts'
assert_not_contains "$tasks" 'node@24"'
assert_not_contains "$tasks" 'corepack enable'
assert_not_contains "$tasks" 'pmOnFail'
assert_not_contains "$smoke_tasks" 'pmOnFail'

printf 'ok - pinned JavaScript toolchain declaration\n'
