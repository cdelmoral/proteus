#!/usr/bin/env bash

proteus_config_value() {
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
