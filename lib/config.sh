#!/usr/bin/env bash

readonly _proteus_config_file="${XDG_CONFIG_HOME:-$HOME/.config}/proteus/config"
readonly _proteus_github_reference_key='github_token_1password_reference'

_proteus_config_value() {
  local file_path="$1"
  local target_key="$2"
  local parsed_key parsed_value result=''

  while IFS='=' read -r parsed_key parsed_value || [[ -n "$parsed_key" ]]; do
    if [[ "$parsed_key" == "$target_key" ]]; then
      result="$parsed_value"
    fi
  done <"$file_path"

  printf '%s' "$result"
}

proteus_github_reference() {
  if [[ ! -f "$_proteus_config_file" ]]; then
    return 0
  fi

  _proteus_config_value "$_proteus_config_file" "$_proteus_github_reference_key"
}

proteus_save_github_reference() {
  local reference="$1"
  local config_dir="${_proteus_config_file%/*}"
  local temporary_file

  mkdir -p "$config_dir"
  umask 077
  temporary_file="$(mktemp "${_proteus_config_file}.XXXXXX")"
  trap 'rm -f "$temporary_file"' RETURN
  printf '%s=%s\n' "$_proteus_github_reference_key" "$reference" >"$temporary_file"
  mv "$temporary_file" "$_proteus_config_file"
  trap - RETURN

  printf '%s' "$_proteus_config_file"
}
