#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  printf 'Usage: assert_converged.sh SECOND_RUN_OUTPUT\n' >&2
  exit 2
fi

readonly output_file="$1"

if [[ ! -r "$output_file" ]]; then
  printf 'Second-run output is not readable: %s\n' "$output_file" >&2
  exit 2
fi

recap="$({
  while IFS= read -r line; do
    [[ "$line" == *'changed='* ]] && printf '%s\n' "$line"
  done <"$output_file"
} || true)"

if [[ -z "$recap" ]]; then
  printf 'Could not find an Ansible recap in the second-run output.\n' >&2
  exit 1
fi

while IFS= read -r line; do
  if [[ ! "$line" =~ (^|[[:space:]])changed=0([[:space:]]|$) ]] ||
    [[ ! "$line" =~ (^|[[:space:]])unreachable=0([[:space:]]|$) ]] ||
    [[ ! "$line" =~ (^|[[:space:]])failed=0([[:space:]]|$) ]]; then
    printf 'Second Provisioning run did not converge: %s\n' "$line" >&2
    exit 1
  fi
done <<<"$recap"
