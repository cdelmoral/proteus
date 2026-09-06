#!/usr/bin/env bash
set -euo pipefail

repository_root="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"
readonly repository_root
readonly convergence_check="${repository_root}/tests/assert_converged.sh"
readonly workflow="${repository_root}/.github/workflows/ci.yml"
readonly integration="${repository_root}/tests/ci_integration.sh"
test_directory="$(mktemp -d)"
readonly test_directory
trap 'rm -rf "$test_directory"' EXIT

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

assert_contains() {
  local haystack="$1"
  local needle="$2"

  [[ "$haystack" == *"$needle"* ]] || fail "expected content to contain: $needle"
}

assert_not_contains() {
  local haystack="$1"
  local needle="$2"

  [[ "$haystack" != *"$needle"* ]] || fail "expected content not to contain: $needle"
}

valid_recap="${test_directory}/valid-recap"
printf '%s\n' \
  'PLAY RECAP *********************************************************************' \
  '127.0.0.1 : ok=52 changed=0 unreachable=0 failed=0 skipped=3 rescued=0 ignored=0' \
  >"$valid_recap"
"$convergence_check" "$valid_recap"

for counter in changed unreachable failed; do
  invalid_recap="${test_directory}/${counter}-recap"
  case "$counter" in
    changed)
      recap_line='127.0.0.1 : ok=52 changed=1 unreachable=0 failed=0'
      ;;
    unreachable)
      recap_line='127.0.0.1 : ok=52 changed=0 unreachable=1 failed=0'
      ;;
    failed)
      recap_line='127.0.0.1 : ok=52 changed=0 unreachable=0 failed=1'
      ;;
  esac
  printf '%s\n' "$recap_line" >"$invalid_recap"

  if "$convergence_check" "$invalid_recap" >/dev/null 2>&1; then
    fail "accepted a nonzero $counter counter"
  fi
done

missing_recap="${test_directory}/missing-recap"
printf '%s\n' 'PLAY RECAP' >"$missing_recap"
if "$convergence_check" "$missing_recap" >/dev/null 2>&1; then
  fail 'accepted output without a host recap'
fi

workflow_contents="$(<"$workflow")"
integration_contents="$(<"$integration")"

assert_contains "$workflow_contents" 'ubuntu-26.04-arm'
assert_contains "$workflow_contents" 'make static'
assert_contains "$workflow_contents" 'make ci-integration'
assert_contains "$workflow_contents" 'pull_request:'
assert_contains "$workflow_contents" 'branches:'
# These assertions check literal integration-script fragments.
# shellcheck disable=SC2016
assert_contains "$integration_contents" 'ansible-playbook "${playbook_arguments[@]}"'
# shellcheck disable=SC2016
assert_contains "$integration_contents" '--user "$ci_user"'
assert_contains "$integration_contents" 'sudoers.d'
assert_contains "$integration_contents" 'second_run_output'
assert_not_contains "$integration_contents" '--check'
assert_not_contains "$integration_contents" 'connection: local'

printf 'CI contract and convergence tests passed.\n'
