#!/usr/bin/env python3
"""Guest assertions invoked only by lima_acceptance.sh in its disposable VM."""
import json
from pathlib import Path
import subprocess
import sys

phase, workspace = sys.argv[1:]
root = Path(workspace)
mise = str(Path.home() / '.local/bin/mise')


def run(*args, cwd=root, expected=0):
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=300)
    assert result.returncode == expected, (args, result.returncode, result.stdout, result.stderr)
    return result.stdout.strip()


def shell(script, expected=0):
    return run('bash', '-ic', script, expected=expected)


def version(directory, expected):
    observed = shell(f'cd "{directory}"; node -p process.version')
    assert observed == 'v' + expected, (directory, observed, expected)


if phase == 'prepare':
    baseline = run(mise, 'config', 'get', '--global', 'tools.node').strip('"')
    (root / 'baseline').write_text(baseline)
    version(root, baseline)
    # Explicit installation does not change global selection.
    run(mise, 'install', 'node@22.14.0')
    for name, declaration, content in [
        ('nvmrc', '.nvmrc', 'v22.14.0\n'),
        ('node-version', '.node-version', '22.14.0\n'),
        ('mise', 'mise.toml', '[tools]\nnode = "22.14.0"\n'),
    ]:
        project = root / name
        project.mkdir()
        (project / declaration).write_text(content)
        if name == 'mise':
            run(mise, 'trust', str(project / declaration))
        version(project, '22.14.0')
        # Exercise selection across cd in a single interactive shell.
        observed = shell(f'cd "{project}"; node -p process.version; cd "{root}"; node -p process.version')
        assert observed.splitlines() == ['v22.14.0', 'v' + baseline], observed
        (project / 'package.json').write_text(json.dumps({'scripts': {
            'build': 'node build.cjs', 'test': 'node test.cjs', 'failure': 'node -e "process.exit(7)"'
        }}))
        (project / 'build.cjs').write_text(
            'require("node:fs").writeFileSync("runtime.txt", process.version)\n')
        (project / 'test.cjs').write_text(
            'require("node:assert/strict").equal(require("node:fs").readFileSync("runtime.txt", "utf8"), process.version);\n'
            'require("node:assert/strict").equal(process.version, "v22.14.0");\n')
        shell(f'cd "{project}"; pnpm run build && pnpm test')
        assert (project / 'runtime.txt').read_text() == 'v22.14.0'
        shell(f'cd "{project}"; pnpm run failure', expected=7)
    missing = root / 'missing'
    missing.mkdir()
    (missing / '.nvmrc').write_text('20.19.0\n')
    # Fresh acceptance guest must not already contain the requested runtime.
    result = subprocess.run([mise, 'where', 'node@20.19.0'], cwd=root,
                            capture_output=True, timeout=30)
    assert result.returncode != 0, 'Missing-version fixture unexpectedly installed'
    result = subprocess.run(['bash', '-ic', f'cd "{missing}"; node -v'],
                            cwd=root, text=True, capture_output=True, timeout=30)
    assert result.returncode != 0, result.stdout
    assert 'mise install' in result.stderr, result.stderr
    result = subprocess.run([mise, 'where', 'node@20.19.0'], cwd=root,
                            capture_output=True, timeout=30)
    assert result.returncode != 0, 'Execution implicitly installed Node'
    run(mise, 'install', cwd=missing)
    version(missing, '20.19.0')
    version(root / 'nvmrc', '22.14.0')
    version(root, baseline)
    # Deliberately drift the global selection; repeated Provisioning restores it.
    run(mise, 'use', '--global', '--pin', 'node@22.14.0')
elif phase == 'verify':
    baseline = (root / 'baseline').read_text()
    version(root, baseline)
    version(root / 'nvmrc', '22.14.0')
    version(root / 'missing', '20.19.0')
else:
    raise AssertionError(phase)
print('Node selection acceptance passed:', phase)
