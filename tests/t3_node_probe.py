"""Unmodified-environment probe run by a real, already authorized T3 agent.

The local/systemd fixtures do not call this an agent acceptance result. Keep the
T3 command activity alongside the JSON files as provenance; a JSON file alone
cannot establish who executed a command.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

PROVIDERS = ('claude', 'opencode', 'codex')
VERSIONS = {'nvmrc': '22.14.0', 'node-version': '20.19.0', 'mise': '22.14.0'}
MISSING_CANDIDATES = ('18.20.8', '18.20.7', '16.20.2', '22.13.1')


def command(directory, *args):
    # Inherit the actual agent shell's environment. No env -i, PATH rewrite,
    # helper prefix, shell startup injection, or synthetic service here.
    return subprocess.run(args, cwd=directory, text=True, capture_output=True, timeout=60)


def checked(directory, *args):
    result = command(directory, *args)
    assert result.returncode == 0, (args, result.returncode, result.stdout, result.stderr)
    return result.stdout.strip()


def prepare(root):
    mise = str(Path.home() / '.local/bin/mise')
    baseline = checked(root, mise, 'config', 'get', '--global', 'tools.node').strip('"')
    (root / 'baseline').write_text(baseline)
    # These are explicit installations, never downloads during selection.
    for version in sorted(set(VERSIONS.values())):
        checked(root, mise, 'install', 'node@' + version)
    for name, version in VERSIONS.items():
        directory = root / name
        directory.mkdir()
        declaration = {'nvmrc': '.nvmrc', 'node-version': '.node-version', 'mise': 'mise.toml'}[name]
        (directory / declaration).write_text(
            '[tools]\nnode = "' + version + '"\n' if name == 'mise' else version + '\n')
        if name == 'mise':
            checked(directory, mise, 'trust', str(directory / declaration))
        (directory / 'package.json').write_text(json.dumps({'scripts': {
            'build': 'node -e "require(\'fs\').writeFileSync(\'runtime.txt\', process.version)"',
            'test': 'node check.cjs', 'failure': 'node -e "process.exit(7)"'}}))
        (directory / 'check.cjs').write_text(
            'const a = require("node:assert/strict");\n'
            f'a.equal(process.version, "v{version}");\n'
            'a.equal(require("node:fs").readFileSync("runtime.txt", "utf8"), process.version);\n')
    missing_version = next((version for version in MISSING_CANDIDATES
                            if command(root, mise, 'where', 'node@' + version).returncode != 0), None)
    assert missing_version, 'Missing-version fixtures are all installed; choose another valid absent version'
    (root / 'missing').mkdir()
    (root / 'missing/.nvmrc').write_text(missing_version + '\n')
    print('Prepared:', root)
    print('In each authorized T3 provider, run this unprefixed command using its normal shell tool:')
    for provider in PROVIDERS:
        print(f'python3 {root}/probe.py probe {provider}')
    print('Keep the T3 command activity as provenance. Then run --t3-node-verify INSTANCE WORKSPACE.')


def ancestors():
    result = []
    pid = os.getpid()
    for _ in range(12):
        proc = Path('/proc') / str(pid)
        if not proc.exists():
            break
        status = (proc / 'status').read_text().splitlines()
        result.append({'pid': pid, 'name': (proc / 'comm').read_text().strip(),
                       'executable': os.readlink(proc / 'exe')})
        pid = int(next(line.split()[1] for line in status if line.startswith('PPid:')))
        if pid == 0:
            break
    return result


def probe(root, provider):
    assert provider in PROVIDERS, provider
    evidence = root / (provider + '.json')
    evidence.unlink(missing_ok=True)  # A failed retry must not leave stale success.
    assert Path('/usr/local/bin/proteus-project-exec').is_file(), 'Missing managed helper'
    mise = str(Path.home() / '.local/bin/mise')
    baseline = (root / 'baseline').read_text()
    observations = {}
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda name: checked(root / name, 'node', '-p', 'process.version'), VERSIONS))
    for (name, version), observed in zip(VERSIONS.items(), results):
        assert observed == 'v' + version, (name, observed, version, os.environ.get('PATH'))
        directory = root / name
        checked(directory, 'pnpm', 'run', 'build')
        checked(directory, 'pnpm', 'test')
        assert command(directory, 'pnpm', 'run', 'failure').returncode == 7
        observations[name] = observed
    assert checked(root, 'node', '-p', 'process.version') == 'v' + baseline
    switched = checked(root, 'bash', '-c',
                       'node -p process.version; cd "$1"; node -p process.version',
                       'bash', str(root / 'node-version'))
    assert switched.splitlines() == ['v' + baseline, 'v20.19.0'], switched
    missing = root / 'missing'
    missing_version = (missing / '.nvmrc').read_text().strip()
    for tool in ('node', 'npm', 'pnpm'):
        result = command(missing, tool, '--version')
        assert result.returncode != 0 and 'mise install' in result.stderr, (tool, result)
    assert command(root, mise, 'where', 'node@' + missing_version).returncode != 0
    assert checked(root, mise, 'config', 'get', '--global', 'tools.node').strip('"') == baseline
    data = {'provider': provider, 'path': os.environ.get('PATH'), 'ancestors': ancestors(),
            'versions': observations, 'baseline': baseline, 'missing': missing_version, 'passed': True}
    evidence.write_text(json.dumps(data, indent=2) + '\n')
    print(evidence.read_text())


def verify(root):
    for provider in PROVIDERS:
        path = root / (provider + '.json')
        assert path.is_file(), f'Missing actual T3 {provider} probe: {path}'
        data = json.loads(path.read_text())
        assert data['passed'] and data['provider'] == provider
        assert data['versions'] == {key: 'v' + value for key, value in VERSIONS.items()}
        assert data['baseline'] == (root / 'baseline').read_text()
    print('All provider probes passed. Review saved T3 activity to establish execution provenance.')


if __name__ == '__main__':
    action = sys.argv[1]
    root = Path(__file__).resolve().parent
    if action == 'prepare':
        prepare(root)
    elif action == 'probe':
        probe(root, sys.argv[2])
    elif action == 'verify':
        verify(root)
    else:
        raise SystemExit('Expected prepare, probe PROVIDER, or verify')
