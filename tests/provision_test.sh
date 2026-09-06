#!/usr/bin/env bash
set -euo pipefail

readonly repository_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
readonly provision_command="${repository_root}/provision"
test_count=0

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

assert_contains() {
  local haystack="$1"
  local needle="$2"

  [[ "$haystack" == *"$needle"* ]] || fail "expected output to contain: $needle"
}

assert_file_contains_line() {
  local file="$1"
  local expected="$2"

  while IFS= read -r line; do
    [[ "$line" == "$expected" ]] && return 0
  done <"$file"

  fail "expected $file to contain line: $expected"
}

assert_file_excludes() {
  local file="$1"
  local unexpected="$2"

  [[ "$(<"$file")" != *"$unexpected"* ]] || fail "expected $file not to contain: $unexpected"
}

new_test_directory() {
  TEST_DIRECTORY="$(mktemp -d)"
  BIN_DIRECTORY="${TEST_DIRECTORY}/bin"
  mkdir "${BIN_DIRECTORY}"
  SSH_CONFIG="${TEST_DIRECTORY}/ssh.config"
  : >"${SSH_CONFIG}"
}

stub_command() {
  local name="$1"
  shift
  {
    printf '#!/usr/bin/env bash\n'
    printf '%s\n' "$@"
  } >"${BIN_DIRECTORY}/${name}"
  chmod +x "${BIN_DIRECTORY}/${name}"
}

run_test() {
  local name="$1"
  shift

  new_test_directory
  "$@"
  rm -rf "${TEST_DIRECTORY}"
  test_count=$((test_count + 1))
  printf 'ok %d - %s\n' "$test_count" "$name"
}

test_missing_ansible() {
  stub_command limactl 'exit 0'

  local output
  local status=0
  output="$(PATH="${BIN_DIRECTORY}:/usr/bin:/bin" "$provision_command" 2>&1)" || status=$?

  [[ $status -eq 1 ]] || fail "missing Ansible returned $status"
  assert_contains "$output" 'ansible-playbook is required. Install it with: brew install ansible'
}

test_missing_instance() {
  stub_command ansible-playbook 'exit 0'
  stub_command limactl 'exit 1'

  local output
  local status=0
  output="$(PATH="${BIN_DIRECTORY}:/usr/bin:/bin" "$provision_command" 2>&1)" || status=$?

  [[ $status -eq 1 ]] || fail "missing instance returned $status"
  assert_contains "$output" "Lima instance 'proteus' does not exist."
}

test_stopped_instance() {
  stub_command ansible-playbook 'exit 0'
  stub_command limactl "printf '%s\\n' 'Stopped|lima-proteus|${SSH_CONFIG}'"

  local output
  local status=0
  output="$(PATH="${BIN_DIRECTORY}:/usr/bin:/bin" "$provision_command" 2>&1)" || status=$?

  [[ $status -eq 1 ]] || fail "stopped instance returned $status"
  assert_contains "$output" "Lima instance 'proteus' is not running (status: Stopped)."
}

test_unreadable_ssh_config() {
  stub_command ansible-playbook 'exit 0'
  stub_command limactl "printf '%s\\n' 'Running|lima-proteus|${TEST_DIRECTORY}/missing.config'"

  local output
  local status=0
  output="$(PATH="${BIN_DIRECTORY}:/usr/bin:/bin" "$provision_command" 2>&1)" || status=$?

  [[ $status -eq 1 ]] || fail "unreadable SSH config returned $status"
  assert_contains "$output" "Lima SSH configuration is not readable: ${TEST_DIRECTORY}/missing.config"
}

test_ansible_invocation() {
  local arguments_file="${TEST_DIRECTORY}/ansible-arguments"
  local lima_arguments_file="${TEST_DIRECTORY}/lima-arguments"
  stub_command limactl \
    "printf '%s\\n' \"\$@\" >'${lima_arguments_file}'" \
    "printf '%s\\n' 'Running|lima-ticket-2|${SSH_CONFIG}'"
  stub_command ansible-playbook \
    "printf '%s\\n' \"\$@\" >'${arguments_file}'"

  PATH="${BIN_DIRECTORY}:/usr/bin:/bin" PROTEUS_INSTANCE=ticket-2 "$provision_command"

  assert_file_contains_line "$lima_arguments_file" 'list'
  assert_file_contains_line "$lima_arguments_file" '--tty=false'
  assert_file_contains_line "$lima_arguments_file" '--format={{.Status}}|{{.Hostname}}|{{.SSHConfigFile}}'
  assert_file_contains_line "$lima_arguments_file" 'ticket-2'
  assert_file_contains_line "$arguments_file" '--inventory'
  assert_file_contains_line "$arguments_file" 'lima-ticket-2,'
  assert_file_contains_line "$arguments_file" "--ssh-common-args=-F ${SSH_CONFIG}"
  assert_file_contains_line "$arguments_file" "${repository_root}/provisioning/playbook.yml"
  assert_file_excludes "$arguments_file" 'local_preferences_file'
}

test_local_preferences_invocation() {
  local copied_root="${TEST_DIRECTORY}/repository"
  local arguments_file="${TEST_DIRECTORY}/ansible-arguments"
  local preferences_file="${copied_root}/provisioning/local-preferences.yml"
  mkdir -p "${copied_root}/provisioning"
  cp "$provision_command" "${copied_root}/provision"
  printf '%s\n' 'git: {}' >"$preferences_file"
  stub_command limactl "printf '%s\\n' 'Running|lima-proteus|${SSH_CONFIG}'"
  stub_command ansible-playbook \
    "printf '%s\\n' \"\$@\" >'${arguments_file}'"

  PATH="${BIN_DIRECTORY}:/usr/bin:/bin" "${copied_root}/provision"

  assert_file_contains_line "$arguments_file" '--extra-vars'
  assert_file_contains_line \
    "$arguments_file" \
    "{\"local_preferences_file\":\"${preferences_file}\"}"
  assert_file_contains_line "$arguments_file" "${copied_root}/provisioning/playbook.yml"
}

test_ansible_exit_status() {
  stub_command limactl "printf '%s\\n' 'Running|lima-proteus|${SSH_CONFIG}'"
  stub_command ansible-playbook 'exit 42'

  local status=0
  PATH="${BIN_DIRECTORY}:/usr/bin:/bin" "$provision_command" >/dev/null 2>&1 || status=$?

  [[ $status -eq 42 ]] || fail "Ansible exit status became $status"
}

test_rejects_arguments() {
  stub_command ansible-playbook 'exit 0'
  stub_command limactl 'exit 0'

  local output
  local status=0
  output="$(PATH="${BIN_DIRECTORY}:/usr/bin:/bin" "$provision_command" --extra-vars danger=true 2>&1)" || status=$?

  [[ $status -eq 2 ]] || fail "invalid arguments returned $status"
  assert_contains "$output" 'Usage: provision'
}

test_pinned_image() {
  local definition="${repository_root}/vm/proteus.yaml"
  local expected_image
  expected_image=$'  - location: >-\n'
  expected_image+=$'      https://cloud-images.ubuntu.com/releases/resolute/release-20260823/ubuntu-26.04-server-cloudimg-arm64.img\n'
  expected_image+=$'    digest: >-\n'
  expected_image+=$'      sha256:00e2d9f09373125eb9040952ae3b8d5553fe3df8f5004c08838473a1f61b74bf\n'
  expected_image+=$'    arch: "aarch64"'

  assert_contains "$(<"$definition")" "$expected_image"
}

test_baseline_package_list() {
  local variables="${repository_root}/provisioning/group_vars/all.yml"
  local expected_packages
  expected_packages=$'baseline_system_packages:\n'
  expected_packages+=$'  - build-essential\n'
  expected_packages+=$'  - ca-certificates\n'
  expected_packages+=$'  - curl\n'
  expected_packages+=$'  - fzf\n'
  expected_packages+=$'  - git\n'
  expected_packages+=$'  - gnupg\n'
  expected_packages+=$'  - jq\n'
  expected_packages+=$'  - neovim\n'
  expected_packages+=$'  - pipx\n'
  expected_packages+=$'  - python3\n'
  expected_packages+=$'  - python3-venv\n'
  expected_packages+=$'  - ripgrep\n'
  expected_packages+=$'  - unzip\n'
  expected_packages+=$'  - wget\n\n'
  expected_packages+=$'baseline_commands:'

  assert_contains "$(<"$variables")" "$expected_packages"
}

test_local_preferences_files() {
  local example="${repository_root}/provisioning/local-preferences.example.yml"
  local expected
  expected=$'---\ngit:\n'
  expected+=$'  name: Example Name\n'
  expected+=$'  email: example@example.invalid'

  [[ "$(<"$example")" == "$expected" ]] || fail 'local preferences example changed unexpectedly'
  git -C "$repository_root" check-ignore --quiet provisioning/local-preferences.yml ||
    fail 'the real local preferences file is not ignored'
}

trap 'rm -rf "${TEST_DIRECTORY:-}"' EXIT

run_test 'reports missing Ansible' test_missing_ansible
run_test 'reports a missing Lima instance' test_missing_instance
run_test 'reports a stopped Lima instance' test_stopped_instance
run_test 'reports an unreadable SSH configuration' test_unreadable_ssh_config
run_test 'uses Lima connection data for Ansible' test_ansible_invocation
run_test 'passes an existing local preferences file to Ansible' test_local_preferences_invocation
run_test 'preserves the Ansible exit status' test_ansible_exit_status
run_test 'rejects unsupported arguments' test_rejects_arguments
run_test 'pins the Ubuntu image and digest' test_pinned_image
run_test 'keeps the existing baseline package set' test_baseline_package_list
run_test 'documents and ignores local preferences' test_local_preferences_files
