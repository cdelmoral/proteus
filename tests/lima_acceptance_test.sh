#!/usr/bin/env bash
set -euo pipefail

readonly repository_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
readonly acceptance_command="${repository_root}/tests/lima_acceptance.sh"
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

assert_not_contains() {
  local haystack="$1"
  local needle="$2"

  [[ "$haystack" != *"$needle"* ]] || fail "expected output not to contain: $needle"
}

new_test_directory() {
  TEST_DIRECTORY="$(mktemp -d)"
  TEST_REPOSITORY="${TEST_DIRECTORY}/repository"
  BIN_DIRECTORY="${TEST_DIRECTORY}/bin"
  LIMA_LOG="${TEST_DIRECTORY}/lima.log"
  PROVISION_LOG="${TEST_DIRECTORY}/provision.log"
  PROVISION_COUNT="${TEST_DIRECTORY}/provision.count"
  mkdir -p "${TEST_REPOSITORY}/tests" "${TEST_REPOSITORY}/vm" "$BIN_DIRECTORY"
  cp "$acceptance_command" "${TEST_REPOSITORY}/tests/lima_acceptance.sh"
  printf '%s\n' 'production VM definition' >"${TEST_REPOSITORY}/vm/proteus.yaml"
  : >"$LIMA_LOG"
  : >"$PROVISION_LOG"
  export LIMA_LOG PROVISION_LOG PROVISION_COUNT
}

stub_command() {
  local path="$1"
  shift
  {
    printf '#!/usr/bin/env bash\n'
    printf 'set -euo pipefail\n'
    printf '%s\n' "$@"
  } >"$path"
  chmod +x "$path"
}

install_stubs() {
  stub_command "${BIN_DIRECTORY}/ansible-playbook" 'exit 0'
  stub_command "${BIN_DIRECTORY}/limactl" '
printf "%s\n" "$*" >>"$LIMA_LOG"
case "$1" in
  list)
    if [[ "${LIMA_INSTANCE_EXISTS:-false}" == true ]]; then
      printf "%s\n" "${PROTEUS_ACCEPTANCE_INSTANCE}"
    fi
    ;;
  create)
    exit "${LIMA_CREATE_STATUS:-0}"
    ;;
esac
'
  stub_command "${TEST_REPOSITORY}/provision" '
count=0
[[ ! -f "$PROVISION_COUNT" ]] || count="$(<"$PROVISION_COUNT")"
count=$((count + 1))
printf "%s\n" "$count" >"$PROVISION_COUNT"
printf "%s|%s\n" "$PROTEUS_INSTANCE" "$*" >>"$PROVISION_LOG"
if [[ "$count" -eq 1 ]]; then
  printf "lima-test : ok=30 changed=8 unreachable=0 failed=0\n"
  exit "${FIRST_PROVISION_STATUS:-0}"
fi
printf "lima-test : ok=30 changed=%s unreachable=%s failed=%s\n" \
  "${SECOND_CHANGED:-0}" "${SECOND_UNREACHABLE:-0}" "${SECOND_FAILED:-0}"
'
}

run_acceptance() {
  local status=0
  ACCEPTANCE_OUTPUT="$(
    PATH="${BIN_DIRECTORY}:/usr/bin:/bin" \
      PROTEUS_ACCEPTANCE_INSTANCE=proteus-acceptance-test-123 \
      "${TEST_REPOSITORY}/tests/lima_acceptance.sh" 2>&1
  )" || status=$?
  ACCEPTANCE_STATUS=$status
}

run_test() {
  local name="$1"
  shift

  new_test_directory
  install_stubs
  "$@"
  rm -rf "$TEST_DIRECTORY"
  test_count=$((test_count + 1))
  printf 'ok %d - %s\n' "$test_count" "$name"
}

test_complete_acceptance_lifecycle() {
  run_acceptance

  [[ $ACCEPTANCE_STATUS -eq 0 ]] || fail "acceptance returned $ACCEPTANCE_STATUS: $ACCEPTANCE_OUTPUT"
  local expected_lima_log
  expected_lima_log="validate --tty=false ${TEST_REPOSITORY}/vm/proteus.yaml"$'\n'
  expected_lima_log+="list --tty=false --format={{.Name}} proteus-acceptance-test-123"$'\n'
  expected_lima_log+="create --tty=false --name=proteus-acceptance-test-123 --set=.portForwards=[] ${TEST_REPOSITORY}/vm/proteus.yaml"$'\n'
  expected_lima_log+="start --tty=false proteus-acceptance-test-123"$'\n'
  expected_lima_log+="delete --tty=false --force proteus-acceptance-test-123"
  [[ "$(<"$LIMA_LOG")" == "$expected_lima_log" ]] || fail "unexpected Lima lifecycle: $(<"$LIMA_LOG")"
  [[ "$(<"$PROVISION_COUNT")" == 2 ]] || fail 'Provisioning did not run twice'
  [[ "$(<"$PROVISION_LOG")" == $'proteus-acceptance-test-123|\nproteus-acceptance-test-123|' ]] ||
    fail "Provisioning did not target only the disposable instance: $(<"$PROVISION_LOG")"
  assert_contains "$ACCEPTANCE_OUTPUT" 'Disposable Lima acceptance passed'
}

test_refuses_existing_instance() {
  export LIMA_INSTANCE_EXISTS=true
  run_acceptance

  [[ $ACCEPTANCE_STATUS -eq 1 ]] || fail "existing instance returned $ACCEPTANCE_STATUS"
  assert_contains "$ACCEPTANCE_OUTPUT" 'already exists; refusing to overwrite or adopt it'
  assert_not_contains "$(<"$LIMA_LOG")" 'create '
  assert_not_contains "$(<"$LIMA_LOG")" 'delete '
  [[ ! -s "$PROVISION_LOG" ]] || fail 'Provisioning ran against an existing instance'
  unset LIMA_INSTANCE_EXISTS
}

test_does_not_delete_after_failed_creation() {
  export LIMA_CREATE_STATUS=12
  run_acceptance

  [[ $ACCEPTANCE_STATUS -eq 12 ]] || fail "failed create returned $ACCEPTANCE_STATUS"
  assert_contains "$(<"$LIMA_LOG")" 'create --tty=false --name=proteus-acceptance-test-123'
  assert_not_contains "$(<"$LIMA_LOG")" 'delete '
  [[ ! -s "$PROVISION_LOG" ]] || fail 'Provisioning ran after failed creation'
  unset LIMA_CREATE_STATUS
}

test_cleans_up_after_provisioning_failure() {
  export FIRST_PROVISION_STATUS=17
  run_acceptance

  [[ $ACCEPTANCE_STATUS -eq 17 ]] || fail "failed Provisioning returned $ACCEPTANCE_STATUS"
  assert_contains "$(<"$LIMA_LOG")" 'delete --tty=false --force proteus-acceptance-test-123'
  [[ "$(<"$PROVISION_COUNT")" == 1 ]] || fail 'Provisioning continued after its first failure'
  unset FIRST_PROVISION_STATUS
}

test_rejects_a_nonzero_second_recap() {
  export SECOND_CHANGED=1
  run_acceptance

  [[ $ACCEPTANCE_STATUS -eq 1 ]] || fail "non-convergent run returned $ACCEPTANCE_STATUS"
  assert_contains "$ACCEPTANCE_OUTPUT" 'Second Provisioning run did not converge'
  assert_contains "$(<"$LIMA_LOG")" 'delete --tty=false --force proteus-acceptance-test-123'
  [[ "$(<"$PROVISION_COUNT")" == 2 ]] || fail 'convergence did not use two real runs'
  unset SECOND_CHANGED
}

test_never_accepts_the_production_instance_name() {
  local status=0
  local output
  output="$(
    PATH="${BIN_DIRECTORY}:/usr/bin:/bin" \
      PROTEUS_ACCEPTANCE_INSTANCE=proteus \
      "${TEST_REPOSITORY}/tests/lima_acceptance.sh" 2>&1
  )" || status=$?

  [[ $status -eq 2 ]] || fail "production instance name returned $status"
  assert_contains "$output" "must start with 'proteus-acceptance-'"
  [[ ! -s "$LIMA_LOG" ]] || fail 'Lima was called for the production instance'
  [[ ! -s "$PROVISION_LOG" ]] || fail 'Provisioning was called for the production instance'
}

trap 'rm -rf "${TEST_DIRECTORY:-}"' EXIT

run_test 'uses the production definition and Provisioning command twice' test_complete_acceptance_lifecycle
run_test 'refuses an existing disposable instance' test_refuses_existing_instance
run_test 'does not clean up an instance it failed to create' test_does_not_delete_after_failed_creation
run_test 'cleans up its instance after Provisioning fails' test_cleans_up_after_provisioning_failure
run_test 'requires a zero-change second run and cleans up on failure' test_rejects_a_nonzero_second_recap
run_test 'cannot target the normal proteus instance' test_never_accepts_the_production_instance_name
