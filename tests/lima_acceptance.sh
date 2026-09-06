#!/usr/bin/env bash
set -euo pipefail

repository_root="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"
readonly repository_root
readonly vm_definition="${repository_root}/vm/proteus.yaml"
readonly provision_command="${repository_root}/provision"
readonly convergence_check="${repository_root}/tests/assert_converged.sh"
generated_suffix="$(date -u +%Y%m%d%H%M%S)-$$-${RANDOM}"
readonly generated_suffix
readonly instance="${PROTEUS_ACCEPTANCE_INSTANCE:-proteus-acceptance-${generated_suffix}}"

created=false
second_run_output=''

cleanup() {
  local exit_status=$?

  if [[ "$created" == true ]]; then
    printf "Deleting disposable Lima instance '%s'.\n" "$instance"
    if ! limactl delete --tty=false --force "$instance"; then
      printf "Could not delete disposable Lima instance '%s'.\n" "$instance" >&2
      [[ $exit_status -ne 0 ]] || exit_status=1
    fi
  fi

  [[ -z "$second_run_output" ]] || rm -f "$second_run_output"
  trap - EXIT
  exit "$exit_status"
}

if [[ ! "$instance" =~ ^proteus-acceptance-[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
  printf "Disposable Lima instance name must start with 'proteus-acceptance-': %s\n" "$instance" >&2
  exit 2
fi

if ! command -v limactl >/dev/null 2>&1; then
  printf 'limactl is required. Install it with: brew install lima\n' >&2
  exit 1
fi

if ! command -v ansible-playbook >/dev/null 2>&1; then
  printf 'ansible-playbook is required. Install it with: brew install ansible\n' >&2
  exit 1
fi

limactl validate --tty=false "$vm_definition"

existing_instance="$(
  limactl list --tty=false --format='{{.Name}}' "$instance" 2>/dev/null || true
)"
if [[ -n "$existing_instance" ]]; then
  printf "Lima instance '%s' already exists; refusing to overwrite or adopt it.\n" "$instance" >&2
  exit 1
fi

printf "Creating disposable Lima instance '%s'.\n" "$instance"
limactl create \
  --tty=false \
  --name="$instance" \
  --set='.portForwards=[]' \
  "$vm_definition"
created=true
trap cleanup EXIT

limactl start --tty=false "$instance"

printf "Running Provisioning against '%s'.\n" "$instance"
PROTEUS_INSTANCE="$instance" "$provision_command"

second_run_output="$(mktemp)"
printf "Running Provisioning against '%s' again to verify convergence.\n" "$instance"
PROTEUS_INSTANCE="$instance" "$provision_command" | tee "$second_run_output"

"$convergence_check" "$second_run_output"

printf "Disposable Lima acceptance passed for '%s'.\n" "$instance"
