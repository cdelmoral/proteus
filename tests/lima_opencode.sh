#!/usr/bin/env bash
# Runs only inside the disposable guest owned by lima_acceptance.sh.
set -euo pipefail

state="$HOME/.cache/proteus/opencode-acceptance"
prefix="$("$HOME/.local/bin/mise" where "node@$("$HOME/.local/bin/mise" config get --global tools.node)")"

case "${1:-}" in
  prepare)
    mkdir -p "$state"
    # Exercise migration from the real former npm distribution on the next run.
    PATH="$prefix/bin:$PATH" "$prefix/bin/npm" install --global --no-audit --no-fund opencode-ai@latest
    rm "$HOME/.local/bin/opencode"
    ln -s "$prefix/bin/opencode" "$HOME/.local/bin/opencode"
    python3 - "$state" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

home = Path.home()
files = {
    '.config/opencode/opencode.json': '{"autoupdate":true}\n',
    '.local/share/opencode/auth.json': '{"acceptance":{"type":"api","key":"dummy-not-a-credential"}}\n',
    '.config/opencode/skills/acceptance/SKILL.md': '# Acceptance sentinel\n',
    '.local/share/opencode/acceptance-state': 'session-state sentinel\n',
    '.local/state/opencode/acceptance-state': 'history sentinel\n',
    '.cache/opencode/acceptance-state': 'cache sentinel\n',
    '.opencode/acceptance-state': 'user directory sentinel\n',
}
checksums = {}
for relative, content in files.items():
    path = home / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    # Never replace state created by earlier real commands, even in this guest.
    if not path.exists():
        path.write_text(content)
    checksums[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
(Path(sys.argv[1]) / 'state.json').write_text(json.dumps(checksums))
PY
    ;;
  check)
    [[ ! -e "$prefix/lib/node_modules/opencode-ai" ]]
    [[ ! -e "$prefix/bin/opencode" ]]
    python3 - "$state" <<'PY'
import hashlib
import json
from pathlib import Path
import struct
import sys

home = Path.home()
for relative, checksum in json.loads((Path(sys.argv[1]) / 'state.json').read_text()).items():
    assert hashlib.sha256((home / relative).read_bytes()).hexdigest() == checksum, relative
binary = (home / '.local/share/proteus/opencode/opencode').read_bytes()[:20]
assert binary[:4] == b'\x7fELF', 'Expected a real vendor ELF binary'
assert binary[5] == 1 and struct.unpack('<H', binary[18:20])[0] == 183, 'Expected Linux ARM64'
assert (home / '.local/bin/opencode').resolve() == Path('/usr/local/bin/opencode').resolve()
PY
    mkdir -p "$state/missing-project" "$state/poison"
    printf '99.0.0\n' > "$state/missing-project/.nvmrc"
    printf '[tools]\nnode = "99.0.0"\n' > "$state/missing-project/mise.toml"
    printf '#!/bin/sh\necho "OpenCode tried to use development Node" >&2\nexit 98\n' > "$state/poison/node"
    chmod +x "$state/poison/node"
    cd "$state/missing-project"
    expected="$(OPENCODE_DISABLE_AUTOUPDATE=true "$HOME/.local/share/proteus/opencode/opencode" --version)"
    # No interactive startup, matching background command discovery. A poison
    # Node makes accidental interpreter use fail rather than silently fall back.
    actual="$(env -i HOME="$HOME" PATH="$state/poison:/usr/local/bin:/usr/bin:/bin" \
      bash --noprofile --norc -c 'command -v opencode >&2; opencode --version')"
    [[ "$actual" == "$expected" ]]
    actual="$(bash -ic 'command -v opencode >&2; opencode --version')"
    [[ "$actual" == "$expected" ]]
    [[ ! -d "$HOME/.local/share/mise/installs/node/99.0.0" ]]
    printf 'OpenCode %s: vendor ARM64 binary, shell/background discovery, missing-Node independence, migration and user-state preservation passed.\n' "$actual"
    ;;
  *) printf 'Expected prepare or check.\n' >&2; exit 2 ;;
esac
