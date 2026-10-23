#!/usr/bin/env bash

readonly _proteus_config_file="${XDG_CONFIG_HOME:-$HOME/.config}/proteus/config"
readonly _proteus_github_reference_key='github_token_1password_reference'
readonly _proteus_signing_reference_key='git_signing_key_1password_reference'
readonly _proteus_salesforce_login_url_key='salesforce_login_url'
readonly proteus_default_salesforce_login_url='https://login.salesforce.com'

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

# Rewrites the config file with the given key/value pairs, preserving other keys.
# Avoids associative arrays, which the Bash 3.2 shipped with macOS lacks.
_proteus_save_config_values() {
  local config_dir="${_proteus_config_file%/*}"
  local -a pairs=("$@")
  local temporary_file parsed_key parsed_value index replaced

  mkdir -p "$config_dir"
  umask 077
  temporary_file="$(mktemp "${_proteus_config_file}.XXXXXX")"
  trap 'rm -f "$temporary_file"' RETURN
  if [[ -f "$_proteus_config_file" ]]; then
    while IFS='=' read -r parsed_key parsed_value || [[ -n "$parsed_key" ]]; do
      replaced=false
      for ((index = 0; index < ${#pairs[@]}; index += 2)); do
        if [[ "$parsed_key" == "${pairs[index]}" ]]; then
          replaced=true
        fi
      done
      if [[ "$replaced" == false ]]; then
        printf '%s=%s\n' "$parsed_key" "$parsed_value"
      fi
    done <"$_proteus_config_file" >"$temporary_file"
  fi
  for ((index = 0; index < ${#pairs[@]}; index += 2)); do
    printf '%s=%s\n' "${pairs[index]}" "${pairs[index + 1]}" >>"$temporary_file"
  done
  mv "$temporary_file" "$_proteus_config_file"
  trap - RETURN

  printf '%s' "$_proteus_config_file"
}

proteus_github_reference() {
  if [[ ! -f "$_proteus_config_file" ]]; then
    return 0
  fi

  _proteus_config_value "$_proteus_config_file" "$_proteus_github_reference_key"
}

proteus_signing_reference() {
  if [[ ! -f "$_proteus_config_file" ]]; then
    return 0
  fi

  _proteus_config_value "$_proteus_config_file" "$_proteus_signing_reference_key"
}

# Prints the saved Salesforce login URL, or the standard login URL if none is saved.
proteus_salesforce_login_url() {
  local url=''

  if [[ -f "$_proteus_config_file" ]]; then
    url="$(_proteus_config_value "$_proteus_config_file" "$_proteus_salesforce_login_url_key")"
  fi

  printf '%s' "${url:-$proteus_default_salesforce_login_url}"
}

# Accepts only an https origin on a salesforce.com subdomain, with no
# credentials, port, path, query, or fragment.
proteus_valid_salesforce_login_url() {
  [[ "$1" =~ ^https://([A-Za-z0-9-]+\.)+salesforce\.com$ ]]
}

proteus_save_config() {
  local reference="$1"
  local salesforce_login_url="$2"
  local signing_reference="$3"
  shift 3

  _proteus_save_config_values \
    "$_proteus_github_reference_key" "$reference" \
    "$_proteus_signing_reference_key" "$signing_reference" \
    "$_proteus_salesforce_login_url_key" "$salesforce_login_url" "$@"
}

# Shared contract with host-side setup. Values are data, never sourced as shell.
# shellcheck disable=SC2034 # Public contract consumed by configure and enroll.
proteus_aws_keys=(proteus_aws_account_id proteus_aws_role_arn proteus_aws_region
  proteus_aws_trust_anchor_arn proteus_aws_profile_arn
  proteus_aws_certificate_ref proteus_aws_private_key_ref)

proteus_config_value() {
  if [[ -f "$_proteus_config_file" ]]; then
    _proteus_config_value "$_proteus_config_file" "$1"
  fi
}

proteus_valid_aws_config() {
  local account="$1" role="$2" region="$3" anchor="$4" profile="$5" cert="$6" key="$7"
  local uuid='[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}'
  [[ "$account" =~ ^[0-9]{12}$ &&
     "$role" =~ ^arn:aws:iam::${account}:role/([A-Za-z0-9_+=,.@-]+/)*[A-Za-z0-9_+=,.@-]{1,64}$ &&
     "$region" =~ ^[a-z]{2}-[a-z]+-[0-9]+$ &&
     "$anchor" =~ ^arn:aws:rolesanywhere:${region}:${account}:trust-anchor/${uuid}$ &&
     "$profile" =~ ^arn:aws:rolesanywhere:${region}:${account}:profile/${uuid}$ &&
     "$cert" =~ ^op://[^/]+/[^/]+/.+$ && "$key" =~ ^op://[^/]+/[^/]+/.+$ && "$cert" != "$key" &&
     "$cert$key" != *$'\n'* && "$cert$key" != *$'\r'* ]]
}
