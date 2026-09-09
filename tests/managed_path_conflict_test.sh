#!/usr/bin/env bash
set -euo pipefail

repository_root="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"
readonly repository_root
readonly test_playbook="${repository_root}/tests/managed_path_conflict_test.yml"
test_count=0

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

run_conflict_test() {
  local name="$1"
  local start_task="$2"
  local relative_path="$3"
  local expected_error="$4"
  local test_directory
  local target
  local output
  local status=0

  test_directory="$(mktemp -d)"
  target="${test_directory}/${relative_path}"
  mkdir -p "$(dirname "$target")"
  printf '%s\n' 'unmanaged content' >"$target"

  output="$(ansible-playbook \
    --inventory 'localhost,' \
    --connection local \
    --extra-vars "ansible_user_dir=${test_directory}" \
    --start-at-task "$start_task" \
    "$test_playbook" 2>&1)" || status=$?

  [[ $status -ne 0 ]] || fail "$name did not refuse the unmanaged path"
  if [[ "$output" != *"$expected_error"* ]]; then
    printf '%s\n' "$output" >&2
    fail "$name returned the wrong error"
  fi
  [[ "$(<"$target")" == 'unmanaged content' ]] || fail "$name changed the unmanaged path"

  rm -rf "$test_directory"
  test_count=$((test_count + 1))
  printf 'ok %d - %s\n' "$test_count" "$name"
}

trap 'rm -rf "${test_directory:-}"' EXIT

run_conflict_test \
  'Starship refuses an unmanaged configuration' \
  'Check Starship configuration ownership marker' \
  '.config/starship.toml' \
  'Refusing to replace unmanaged file'

run_conflict_test \
  'OpenCode refuses an unmanaged configuration' \
  'Check OpenCode ownership marker' \
  '.config/opencode/opencode.json' \
  'Refusing to replace unmanaged path'

run_conflict_test \
  'Neovim refuses an unmanaged profile' \
  'Define the managed Neovim profile' \
  '.config/nvim/init.lua' \
  'Refusing to replace unmanaged path'

run_conflict_test \
  'Neovim refuses an unmanaged generated lock' \
  'Define the managed Neovim profile' \
  '.config/nvim/lazy-lock.json' \
  'Refusing to replace unmanaged path'

run_conflict_test \
  'Git refuses an unmanaged main configuration' \
  'Check Git ownership marker' \
  '.gitconfig' \
  'Refusing to replace unmanaged file'
