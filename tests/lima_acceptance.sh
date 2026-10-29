#!/usr/bin/env bash
set -euo pipefail

repository_root="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"
readonly repository_root
readonly vm_definition="${repository_root}/vm/proteus.yaml"
readonly provision_command="${repository_root}/provision"
# Real T3 acceptance is an explicit continuation on an existing authorized guest.
# Never enroll the disposable VM or restart any service to manufacture evidence.
if [[ "${1:-}" == --t3-node-prepare || "${1:-}" == --t3-node-verify ]]; then
  action="$1"
  authorized_instance="${2:?An existing authorized Lima instance is required}"
  if [[ "$action" == --t3-node-prepare ]]; then
    workspace="$(limactl shell --tty=false --start=false "$authorized_instance" mktemp -d /tmp/proteus-t3-node.XXXXXXXX)"
    limactl shell --tty=false --start=false "$authorized_instance" tee "$workspace/probe.py" \
      < "$repository_root/tests/t3_node_probe.py" > /dev/null
    limactl shell --tty=false --start=false "$authorized_instance" python3 "$workspace/probe.py" prepare
  else
    workspace="${3:?The prepared workspace is required}"
    limactl shell --tty=false --start=false "$authorized_instance" python3 "$workspace/probe.py" verify
  fi
  exit
fi

generated_suffix="$(date -u +%Y%m%d%H%M%S)-$$-${RANDOM}"
readonly generated_suffix
readonly instance="${PROTEUS_ACCEPTANCE_INSTANCE:-proteus-acceptance-${generated_suffix}}"

created=false
node_workspace=""

cleanup() {
  local exit_status=$?

  if [[ "$created" == true ]]; then
    printf "Deleting disposable Lima instance '%s'.\n" "$instance"
    if ! limactl delete --tty=false --force "$instance"; then
      printf "Could not delete disposable Lima instance '%s'.\n" "$instance" >&2
      [[ $exit_status -ne 0 ]] || exit_status=1
    fi
  fi

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

check_accepted_release() {
  local accepted requested
  requested="$(cat "$repository_root/VERSION")"
  # HOME must resolve in the guest.
  # shellcheck disable=SC2016
  accepted="$(limactl shell --tty=false --start=false "$instance" sh -c 'cat "$HOME/.local/state/proteus/accepted-version"')"
  [[ "$accepted" == "$requested" ]] || {
    printf 'Expected accepted Proteus release %s, got %s.\n' "$requested" "$accepted" >&2
    return 1
  }
}

printf "Running Provisioning against '%s'.\n" "$instance"
"$provision_command" "$instance"
check_accepted_release

# Check fresh tool installs and seed dummy state for the repeated run.
for phase in fresh prepare; do
  for tool in claude salesforce t3; do
    limactl shell --tty=false --start=false "$instance" python3 - "$phase" \
      < "$repository_root/tests/${tool}_guest_acceptance.py"
  done
done

printf "Preparing OpenCode preservation checks in '%s'.\n" "$instance"
limactl shell --tty=false --start=false "$instance" bash -s -- prepare < "$repository_root/tests/lima_opencode.sh"

printf 'Checking interactive and systemd-background project Node selection in the disposable guest.\n'
node_workspace="$(limactl shell --tty=false --start=false "$instance" mktemp -d /tmp/proteus-node-acceptance.XXXXXXXX)"
limactl shell --tty=false --start=false "$instance" python3 - prepare "$node_workspace" \
  < "$repository_root/tests/lima_node_selection.py"

printf "Repeating Provisioning against '%s' to verify compatible release acceptance, service preservation, user state, and Node restoration.\n" "$instance"
"$provision_command" "$instance"
check_accepted_release
for tool in claude salesforce t3; do
  limactl shell --tty=false --start=false "$instance" python3 - repeated \
    < "$repository_root/tests/${tool}_guest_acceptance.py"
done
limactl shell --tty=false --start=false "$instance" python3 - verify "$node_workspace" \
  < "$repository_root/tests/lima_node_selection.py"
limactl shell --tty=false --start=false "$instance" bash -s -- check < "$repository_root/tests/lima_opencode.sh"

printf "Disposable Lima component acceptance passed (real T3 provider acceptance is separate) for '%s'.\n" "$instance"
