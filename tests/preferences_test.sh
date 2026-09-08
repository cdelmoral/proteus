#!/usr/bin/env bash
set -euo pipefail

repository_root="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"
readonly repository_root
readonly test_playbook="${repository_root}/tests/preferences_test.yml"
test_count=0

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

assert_equals() {
  local actual="$1"
  local expected="$2"

  [[ "$actual" == "$expected" ]] || fail "expected '$expected', got '$actual'"
}

assert_contains() {
  local haystack="$1"
  local needle="$2"

  [[ "$haystack" == *"$needle"* ]] || fail "expected output to contain: $needle"
}

new_test_directory() {
  TEST_DIRECTORY="$(mktemp -d)"
  GIT_CONFIG_GLOBAL="${TEST_DIRECTORY}/gitconfig"
  export GIT_CONFIG_GLOBAL
}

git_value() {
  git config --global --get "$1" 2>/dev/null || true
}

run_preferences() {
  local fixture="${1:-}"
  local arguments=(
    --inventory "localhost,"
    --connection local
  )

  if [[ -n "$fixture" ]]; then
    arguments+=(--extra-vars "local_preferences_file=${fixture}")
  fi

  ansible-playbook "${arguments[@]}" "$test_playbook"
}

assert_second_run_unchanged() {
  local fixture="${1:-}"
  local output
  output="$(run_preferences "$fixture")"
  assert_contains "$output" 'changed=0'
  assert_contains "$output" 'failed=0'
}

run_test() {
  local name="$1"
  shift

  new_test_directory
  "$@"
  rm -rf "$TEST_DIRECTORY"
  test_count=$((test_count + 1))
  printf 'ok %d - %s\n' "$test_count" "$name"
}

test_absent_preferences() {
  git config --global user.name 'Existing Test Name'
  git config --global user.email 'existing@example.invalid'

  run_preferences >/dev/null
  assert_second_run_unchanged

  assert_equals "$(git_value user.name)" 'Existing Test Name'
  assert_equals "$(git_value user.email)" 'existing@example.invalid'
}

test_complete_preferences() {
  local fixture="${TEST_DIRECTORY}/preferences.yml"
  printf '%s\n' \
    'git:' \
    '  name: Complete Test User' \
    '  email: complete@example.invalid' >"$fixture"

  run_preferences "$fixture" >/dev/null
  assert_second_run_unchanged "$fixture"

  assert_equals "$(git_value user.name)" 'Complete Test User'
  assert_equals "$(git_value user.email)" 'complete@example.invalid'
}

test_partial_preferences() {
  local fixture="${TEST_DIRECTORY}/preferences.yml"
  git config --global user.email 'preserved@example.invalid'
  printf '%s\n' \
    'git:' \
    '  name: Partial Test User' >"$fixture"

  run_preferences "$fixture" >/dev/null
  assert_second_run_unchanged "$fixture"

  assert_equals "$(git_value user.name)" 'Partial Test User'
  assert_equals "$(git_value user.email)" 'preserved@example.invalid'
}

assert_invalid_fixture() {
  local fixture_content="$1"
  local expected_error="$2"
  local fixture="${TEST_DIRECTORY}/preferences.yml"
  printf '%s\n' "$fixture_content" >"$fixture"

  local output
  local status=0
  output="$(run_preferences "$fixture" 2>&1)" || status=$?

  [[ $status -ne 0 ]] || fail 'invalid preferences succeeded'
  assert_contains "$output" "$expected_error"
}

test_unknown_top_level_preference() {
  assert_invalid_fixture \
    $'packages:\n  - curl' \
    'Unsupported local preference fields. Allowed fields: git.'
}

test_unknown_git_preference() {
  assert_invalid_fixture \
    $'git:\n  token: not-a-real-token' \
    'Unsupported Git preference fields. Allowed fields: name, email.'
}

test_wrong_type_preference() {
  assert_invalid_fixture \
    $'git:\n  name:\n    - Not\n    - A string' \
    'Git name must be a non-empty string when provided.'
}

test_empty_preference() {
  assert_invalid_fixture \
    $'git:\n  email: ""' \
    'Git email must be a non-empty string when provided.'
}

trap 'rm -rf "${TEST_DIRECTORY:-}"' EXIT

command -v ansible-playbook >/dev/null 2>&1 || fail 'ansible-playbook is required to test local preferences'

run_test 'leaves Git identity untouched when preferences are absent' test_absent_preferences
run_test 'applies complete Git preferences and converges' test_complete_preferences
run_test 'applies partial Git preferences and preserves omitted values' test_partial_preferences
run_test 'rejects unknown top-level preferences' test_unknown_top_level_preference
run_test 'rejects unknown Git preferences' test_unknown_git_preference
run_test 'rejects preference values with the wrong type' test_wrong_type_preference
run_test 'rejects empty preference values' test_empty_preference
