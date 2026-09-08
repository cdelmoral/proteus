#!/usr/bin/env bash
set -euo pipefail

repository_root="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"
readonly repository_root
second_run_output="$(mktemp)"
readonly second_run_output
trap 'rm -f "$second_run_output"' EXIT

assert_converges() {
  local mode="$1"
  shift

  "${repository_root}/provision" "$@"
  "${repository_root}/provision" "$@" | tee "$second_run_output"

  "${repository_root}/tests/assert_converged.sh" "$second_run_output" || {
    printf 'Second %s Provisioning run failed its convergence check.\n' "$mode" >&2
    exit 1
  }
}

assert_converges normal
assert_converges upgrade --upgrade
