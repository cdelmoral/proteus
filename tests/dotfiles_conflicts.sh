#!/usr/bin/env bash
set -euo pipefail

repository_root="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"
readonly repository_root

for command in ansible-playbook stow; do
  if ! command -v "$command" >/dev/null 2>&1; then
    printf '%s is required for the Managed Dotfiles regression test.\n' "$command" >&2
    exit 1
  fi
done

work_dir="$(mktemp -d "${TMPDIR:-/tmp}/proteus-dotfiles.XXXXXX")"
readonly work_dir
readonly test_home="${work_dir}/home"
readonly installed_source="${work_dir}/installed"
trap 'rm -rf "$work_dir"' EXIT

mkdir -p "$test_home"
printf '%s\n' 'Ubuntu image Bash configuration' >"${test_home}/.bashrc"
printf '%s\n' 'Ubuntu image Git configuration' >"${test_home}/.gitconfig"

run_dotfiles_tasks() {
  ansible-playbook \
    --inventory localhost, \
    --skip-tags dotfiles_dependency \
    --extra-vars "ansible_user_dir=${test_home}" \
    --extra-vars "ansible_user_id=$(id -un)" \
    --extra-vars "ansible_user_gid=$(id -g)" \
    --extra-vars "managed_dotfiles_dir=${installed_source}" \
    --extra-vars "managed_dotfiles_source_dir=${repository_root}/dotfiles/" \
    "${repository_root}/tests/dotfiles_conflicts.yml"
}

run_dotfiles_tasks
[[ -L "${test_home}/.bashrc" ]]
[[ -L "${test_home}/.gitconfig" ]]

rm "${test_home}/.bashrc"
printf '%s\n' 'unexpected replacement' >"${test_home}/.bashrc"

if run_dotfiles_tasks; then
  printf 'Provisioning accepted an unexpected replacement for .bashrc.\n' >&2
  exit 1
fi

[[ "$(<"${test_home}/.bashrc")" == 'unexpected replacement' ]]
[[ -L "${test_home}/.gitconfig" ]]
printf 'Managed Dotfiles conflict regression passed.\n'
