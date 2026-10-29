#!/usr/bin/env python3
"""Guest assertions invoked only by lima_acceptance.sh in its disposable VM."""
import json
from pathlib import Path
import subprocess
import sys

phase, workspace = sys.argv[1:]
root = Path(workspace)
mise = str(Path.home() / '.local/bin/mise')
background_path = '/usr/local/bin:/usr/bin:/bin'


def background_command(directory, *args, path=background_path):
    # A real transient user service: no SSH/session PATH or shell startup files.
    # This needs the guest user manager, but never installs/restarts T3.
    return ['systemd-run', '--user', '--wait', '--pipe', '--collect', '--quiet',
            '--property=WorkingDirectory=' + str(directory),
            '/usr/bin/env', '-i', 'HOME=' + str(Path.home()), 'PATH=' + path,
            *args]


def background(directory, *args, expected=0, path=background_path):
    return run(*background_command(directory, *args, path=path), expected=expected)


def background_assertions(baseline):
    projects = [(root, baseline), (root / 'nvmrc', '22.14.0'),
                (root / 'node-version', '22.14.0'), (root / 'mise', '22.14.0'),
                (root / 'missing', '20.19.0')]
    for directory, selected in projects:
        assert background(directory, 'node', '-p', 'process.version') == 'v' + selected
        assert background(directory, 'npm', 'exec', '--offline', '--',
                          'node', '-p', 'process.version') == 'v' + selected
    # Launch both services before waiting: distinct working directories and Node
    # versions must coexist, and global selection must remain unchanged.
    children = [(subprocess.Popen(background_command(directory, 'node', '-e',
                 'setTimeout(() => console.log(process.version), 500)'),
                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True), selected)
                for directory, selected in [projects[1], projects[-1]]]
    for child, selected in children:
        stdout, stderr = child.communicate(timeout=30)
        assert child.returncode == 0, stderr
        assert stdout.strip() == 'v' + selected, stdout
    assert run(mise, 'config', 'get', '--global', 'tools.node').strip('"') == baseline
    observed = background(root, 'sh', '-c',
                          'node -p process.version; cd "$1"; node -p process.version',
                          'sh', str(root / 'nvmrc'))
    assert observed.splitlines() == ['v' + baseline, 'v22.14.0'], observed

    # A real Node parent on the baseline remains on that runtime. Its child
    # starts with a deliberately contaminated service PATH, then uses the
    # explicit project entrypoint; pnpm scripts must run on the project Node.
    parent = root / 'parent.cjs'
    parent.write_text('''
const assert = require('node:assert/strict');
const {spawnSync} = require('node:child_process');
const [directory, baseline] = process.argv.slice(2);
assert.equal(process.version, 'v' + baseline);
for (const args of [['pnpm', 'run', 'build'], ['pnpm', 'test'],
                    ['npm', 'exec', '--offline', '--', 'node', '-p', 'process.version']]) {
  const result = spawnSync('/usr/local/bin/proteus-project-exec', args,
                           {cwd: directory, env: process.env, encoding: 'utf8'});
  assert.equal(result.status, 0, result.stderr);
  if (args[0] === 'npm') assert.equal(result.stdout.trim(), 'v22.14.0');
}
const failure = spawnSync('/usr/local/bin/proteus-project-exec',
                          ['pnpm', 'run', 'failure'], {cwd: directory, env: process.env});
assert.equal(failure.status, 7);
const argument = 'argument with spaces; $literal';
const forwarded = spawnSync('/usr/local/bin/proteus-project-exec',
  ['node', '-e', 'console.log(process.argv[1])', argument],
  {cwd: directory, env: process.env, encoding: 'utf8'});
assert.equal(forwarded.status, 0, forwarded.stderr);
assert.equal(forwarded.stdout.trim(), argument);
assert.equal(process.version, 'v' + baseline);
console.log('parent/child passed');
''')
    baseline_bin = run(mise, 'where', 'node@' + baseline) + '/bin'
    assert background(root, baseline_bin + '/node', str(parent), str(root / 'nvmrc'), baseline,
                      path=baseline_bin + ':' + background_path) == 'parent/child passed'


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
    # Native Proteus tools must be usable to prepare this missing-runtime
    # project. No authentication or provider task is required for --version.
    background(missing, '/usr/local/bin/opencode', '--version')
    for command in [('node', '-v'), ('npm', '--version'), ('pnpm', '--version'),
                    ('proteus-project-exec', 'node', '-v')]:
        result = subprocess.run(background_command(missing, *command),
                                text=True, capture_output=True, timeout=30)
        assert result.returncode != 0, (command, result.stdout)
        assert 'mise install' in result.stderr, (command, result.stderr)
    assert subprocess.run([mise, 'where', 'node@20.19.0'], cwd=root,
                          capture_output=True, timeout=30).returncode != 0
    # Agent recovery uses the very same explicit install operation as a human.
    baseline_bin = run(mise, 'where', 'node@' + baseline) + '/bin'
    for command in ['node', 'npm', 'pnpm']:
        result = subprocess.run(background_command(
            missing, '/usr/local/bin/proteus-project-exec', command, '--version',
            path=baseline_bin + ':' + background_path),
            text=True, capture_output=True, timeout=30)
        assert result.returncode != 0, (command, result.stdout)
        assert 'mise install' in result.stderr, (command, result.stderr)
    background(missing, '/usr/local/bin/proteus-project-exec', mise, 'install', 'node',
               path=baseline_bin + ':' + background_path)
    version(missing, '20.19.0')
    version(root / 'nvmrc', '22.14.0')
    version(root, baseline)
    background_assertions(baseline)
    # Deliberately drift the global selection; repeated Provisioning restores it.
    run(mise, 'use', '--global', '--pin', 'node@22.14.0')
elif phase == 'verify':
    baseline = (root / 'baseline').read_text()
    version(root, baseline)
    version(root / 'nvmrc', '22.14.0')
    version(root / 'missing', '20.19.0')
    background_assertions(baseline)
else:
    raise AssertionError(phase)
print('Node selection acceptance passed:', phase)
