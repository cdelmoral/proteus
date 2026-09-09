#!/usr/bin/env bash
set -euo pipefail

repository_root="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"
readonly repository_root
test_count=0

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

assert_contains() {
  local file="$1"
  local expected="$2"

  [[ "$(<"$file")" == *"$expected"* ]] || fail "expected $file to contain: $expected"
}

assert_excludes() {
  local file="$1"
  local unexpected="$2"

  [[ "$(<"$file")" != *"$unexpected"* ]] || fail "expected $file not to contain: $unexpected"
}

run_test() {
  local name="$1"
  shift

  "$@"
  test_count=$((test_count + 1))
  printf 'ok %d - %s\n' "$test_count" "$name"
}

test_prompt_contract() {
  local config="${repository_root}/provisioning/files/starship/starship.toml"
  local tasks="${repository_root}/provisioning/tasks/prompt.yml"
  local variables="${repository_root}/provisioning/group_vars/all.yml"

  assert_contains "$config" 'format = """'
  # Dollar signs are literal Starship module names.
  # shellcheck disable=SC2016
  assert_contains "$config" '$directory$git_branch$git_status$cmd_duration'
  # shellcheck disable=SC2016
  assert_contains "$config" '$status$character'
  # shellcheck disable=SC2016
  assert_excludes "$config" '$nodejs'
  # shellcheck disable=SC2016
  assert_excludes "$config" '$aws'
  assert_contains "$variables" $'prompt_packages:\n  - starship'
  assert_contains "$tasks" 'starship init bash'
  assert_contains "$tasks" 'Proteus Starship prompt'
}

test_opencode_contract() {
  local variables="${repository_root}/provisioning/group_vars/all.yml"
  local config="${repository_root}/provisioning/files/opencode/opencode.json"
  local tui="${repository_root}/provisioning/files/opencode/tui.json"
  local tasks="${repository_root}/provisioning/tasks/opencode.yml"

  assert_contains "$variables" 'opencode_version: "1.18.29"'
  assert_contains "$variables" 'sha256:70baf769395ca4e7a68924026530c390eace194f3b7e4919d4efcb2aa2eed3c0'
  assert_contains "$config" '"autoupdate": false'
  assert_contains "$config" '"model": "openai/gpt-5.6-sol"'
  assert_contains "$config" $'"*": "ask",\n          "find *": "allow"'
  assert_contains "$tui" '"theme": "nightowl"'
  assert_excludes "$config" 'atlassian'
  assert_excludes "$config" 'jira'
  assert_contains "$tasks" 'Refuse unmanaged OpenCode paths'
  assert_excludes "$tasks" 'auth.json'
}

test_neovim_contract() {
  local profile="${repository_root}/provisioning/files/nvim"
  local extras="${profile}/lazyvim.json"
  local tasks="${repository_root}/provisioning/tasks/neovim.yml"
  local all_profile_files
  all_profile_files="$(find "$profile" -type f -print0 | xargs -0 cat)"

  assert_contains "$extras" 'lazyvim.plugins.extras.editor.harpoon2'
  assert_contains "$extras" 'lazyvim.plugins.extras.lang.typescript'
  assert_contains "$extras" 'lazyvim.plugins.extras.lang.json'
  assert_contains "$extras" 'lazyvim.plugins.extras.lang.yaml'
  assert_contains "$extras" 'lazyvim.plugins.extras.lang.markdown'
  assert_contains "$extras" 'lazyvim.plugins.extras.lang.docker'
  assert_contains "$extras" 'lazyvim.plugins.extras.lang.terraform'
  [[ "$all_profile_files" == *'catppuccin'* ]] || fail 'Neovim profile does not select Catppuccin'
  [[ "$all_profile_files" == *'oil.nvim'* ]] || fail 'Neovim profile does not configure Oil'
  [[ "$all_profile_files" == *'diffview.nvim'* ]] || fail 'Neovim profile does not configure Diffview'
  [[ "$all_profile_files" != *'opencode'* ]] || fail 'Neovim profile includes OpenCode'
  [[ "$all_profile_files" != *'tmux'* ]] || fail 'Neovim profile includes tmux'
  [[ "$all_profile_files" != *'kanagawa'* ]] || fail 'Neovim profile includes Kanagawa'
  assert_contains "$tasks" 'Lazy! sync'
  assert_contains "$tasks" "neovim_managed_files + ['lazy-lock.json']"
  assert_contains "$tasks" 'neovim-ready'
  [[ ! -e "${profile}/lazy-lock.json" ]] || fail 'the LazyVim lock file must be generated during Provisioning'
}

test_git_contract() {
  local config="${repository_root}/provisioning/files/git/gitconfig"
  local ignore="${repository_root}/provisioning/files/git/gitignore_global"
  local tasks="${repository_root}/provisioning/tasks/git.yml"
  local variables="${repository_root}/provisioning/group_vars/all.yml"

  assert_contains "$config" $'\tpager = delta'
  assert_contains "$config" $'\tdiffFilter = delta --color-only'
  assert_contains "$config" $'\ttool = nvimdiff'
  assert_contains "$config" $'\ttool = diffview'
  assert_contains "$config" $'\tconflictStyle = zdiff3'
  assert_contains "$config" $'\tlg = log --oneline --graph --decorate --all'
  assert_contains "$config" '.gitconfig.local'
  assert_excludes "$config" '[user]'
  assert_excludes "$config" 'gpgsign'
  assert_contains "$ignore" 'AGENTS.md'
  assert_contains "$variables" $'git_workflow_packages:\n  - git-delta'
  assert_contains "$tasks" 'Refuse an unmanaged Git configuration'
}

test_playbook_wiring() {
  local playbook="${repository_root}/provisioning/playbook.yml"
  local smoke="${repository_root}/provisioning/tasks/smoke.yml"
  local playbook_contents
  playbook_contents="$(<"$playbook")"

  assert_contains "$playbook" 'tasks/prompt.yml'
  assert_contains "$playbook" 'tasks/opencode.yml'
  assert_contains "$playbook" 'tasks/neovim.yml'
  assert_contains "$playbook" 'tasks/git.yml'
  assert_contains "$smoke" 'prompt_smoke.yml'
  assert_contains "$smoke" 'opencode_smoke.yml'
  assert_contains "$smoke" 'neovim_smoke.yml'
  assert_contains "$smoke" 'git_smoke.yml'

  [[ "${playbook_contents%%tasks/neovim.yml*}" != "$playbook_contents" ]] || fail 'Neovim is not wired'
  local after_neovim="${playbook_contents#*tasks/neovim.yml}"
  [[ "$after_neovim" == *'tasks/git.yml'* ]] || fail 'Git must be provisioned after Neovim'
  local after_git="${playbook_contents#*tasks/git.yml}"
  [[ "$after_git" == *'tasks/preferences.yml'* ]] || fail 'preferences must be applied after Git'
}

run_test 'declares the Bash prompt' test_prompt_contract
run_test 'declares pinned OpenCode configuration' test_opencode_contract
run_test 'declares the minimal LazyVim profile' test_neovim_contract
run_test 'declares the Git workflow' test_git_contract
run_test 'wires workstation tools in dependency order' test_playbook_wiring
