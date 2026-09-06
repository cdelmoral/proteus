#!/usr/bin/env bash
set -euo pipefail

readonly baseline_pnpm="$HOME/.local/share/proteus/pnpm/12.3.4/pnpm"
readonly mise="$HOME/.local/bin/mise"
readonly expected_project_pnpm_version="12.3.3"
project_directory="$(mktemp -d)"
readonly project_directory
trap 'rm -rf "$project_directory"' EXIT

printf '%s\n' \
  '{' \
  '  "name": "proteus-pnpm-version-test",' \
  '  "version": "1.0.0",' \
  '  "packageManager": "pnpm@12.3.3"' \
  '}' \
  >"${project_directory}/package.json"

managed_node="$($mise where node@24.20.0)"
readonly managed_node
readonly managed_path="${managed_node}/bin:/usr/bin:/bin"

if PATH="$managed_path" /usr/bin/env sh -c 'command -v corepack >/dev/null'; then
  printf 'Corepack is present in the managed JavaScript environment.\n' >&2
  exit 1
fi

project_pnpm_version="$(
  cd "$project_directory"
  PATH="$managed_path" "$baseline_pnpm" --version
)"
readonly project_pnpm_version

if [[ "$project_pnpm_version" != "$expected_project_pnpm_version" ]]; then
  printf 'Expected project pnpm %s, found %s.\n' \
    "$expected_project_pnpm_version" "$project_pnpm_version" >&2
  exit 1
fi

printf 'pnpm selected project version %s without Corepack.\n' "$project_pnpm_version"
