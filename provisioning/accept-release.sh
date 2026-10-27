#!/bin/sh
# Runs through Ansible raw before Python/bootstrap. The marker means accepted,
# not completed: interrupted installs/upgrades may retry, never roll back.
set -eu
export LC_ALL=C
newline='
'
requested=${1%"$newline"}
marker="$HOME/.local/state/proteus/accepted-version"
installed='<unversioned>'
has_marker=false
if [ -e "$marker" ] || [ -L "$marker" ]; then
    has_marker=true
    if [ ! -f "$marker" ] || [ ! -r "$marker" ] || [ -L "$marker" ]; then
        installed='<unreadable or invalid marker>'
    else
        # Preserve all bytes/newlines except one optional final newline.
        installed=$(cat "$marker" && printf '.') || exit 1
        installed=${installed%.}
        # Shell variables cannot retain NUL bytes. Reject binary corruption
        # instead of silently turning it into an apparently valid version.
        if [ "${#installed}" -ne "$(wc -c < "$marker")" ]; then
            installed='<corrupt marker>'
        fi
        installed=${installed%"$newline"}
    fi
fi
refuse() {
    printf 'Proteus release refused: installed/accepted [%s], requested [%s]. %s\nPreserve project work, rebuild a fresh VM, and repeat Credential Enrollment. No VM was deleted or rebuilt.\n' \
        "$installed" "$requested" "$1" >&2
    exit 1
}
export installed requested
if ! awk 'BEGIN {
    pattern = "^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)$"
    exit !(ENVIRON["requested"] ~ pattern)
}'; then
    refuse 'Invalid repository VERSION; use a release with canonical major.minor.patch integers.'
fi
if [ "$has_marker" = false ]; then
    # This namespace holds Proteus mise and Managed Dotfiles, including before
    # standalone tools existed. Do not scan vendor packages or credential state.
    if [ -e "$HOME/.local/share/proteus" ] || [ -L "$HOME/.local/share/proteus" ]; then
        refuse 'Previously provisioned unversioned guest; a rebuild is required.'
    fi
elif ! awk 'BEGIN {
    old = ENVIRON["installed"]; new = ENVIRON["requested"]
    pattern = "^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)$"
    if (old !~ pattern) exit 1
    split(old, a, "."); split(new, b, ".")
    if ("x" a[1] != "x" b[1]) exit 1
    # Compare integer strings by length then lexical order, without overflow.
    for (i = 2; i <= 3; i++) {
        if (length(a[i]) != length(b[i])) exit !(length(a[i]) < length(b[i]))
        if ("x" a[i] != "x" b[i]) exit !("x" a[i] < "x" b[i])
    }
}'; then
    refuse 'Invalid accepted version, incompatible major release, or downgrade; a rebuild is required.'
fi
# Atomic rename leaves either the previous accepted release or the new one if
# interrupted; baseline mutations only begin after this command succeeds.
if [ "$installed" != "$requested" ]; then
    mkdir -p "${marker%/*}"
    temporary=$(mktemp "${marker}.XXXXXX")
    trap 'rm -f "$temporary"' EXIT HUP INT TERM
    printf '%s\n' "$requested" > "$temporary"
    mv -f "$temporary" "$marker"
    printf '%s\n' '__PROTEUS_RELEASE_ACCEPTED__'
fi
