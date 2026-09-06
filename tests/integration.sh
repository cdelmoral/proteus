#!/usr/bin/env bash
set -euo pipefail

readonly repository_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
readonly second_run_output="$(mktemp)"
trap 'rm -f "$second_run_output"' EXIT

"${repository_root}/provision"
"${repository_root}/provision" | tee "$second_run_output"

recap="$(
  while IFS= read -r line; do
    [[ "$line" == *'changed='* ]] && printf '%s\n' "$line"
  done <"$second_run_output"
)"

[[ -n "$recap" ]] || {
  printf 'Could not find the Ansible recap for the second run.\n' >&2
  exit 1
}

[[ "$recap" == *'changed=0'* && "$recap" == *'unreachable=0'* && "$recap" == *'failed=0'* ]] || {
  printf 'Second Provisioning run did not converge: %s\n' "$recap" >&2
  exit 1
}
