"""Real T3 artifact/service assertions for the existing disposable Lima flow.

No Connect authorization or real Credential Enrollment is performed here.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

home = Path.home()
phase = sys.argv[1]
record = home / '.cache/proteus/t3-acceptance.json'
environment = {'HOME': str(home), 'PATH': '/usr/local/bin:/usr/bin:/bin',
               'XDG_CONFIG_HOME': str(home / '.config'),
               'XDG_RUNTIME_DIR': os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')}


def run(*command, **kwargs):
    result = subprocess.run(command, capture_output=True, text=True, timeout=180,
                            **{'env': environment, **kwargs})
    assert result.returncode == 0, (command, result.stdout, result.stderr)
    return result.stdout.strip()


def service():
    output = run('systemctl', '--user', 'show', 't3code.service',
                 '--property=MainPID,InvocationID,ExecMainStartTimestamp,ActiveState,UnitFileState')
    properties = dict(line.split('=', 1) for line in output.splitlines() if '=' in line)
    assert properties['ActiveState'] == 'active', properties
    assert properties['UnitFileState'] == 'enabled', properties
    assert int(properties['MainPID']) > 1, properties
    return properties


def snapshot():
    files = [home / '.config/systemd/user/t3code.service', home / '.t3/service.env',
             home / '.t3/userdata/secrets/proteus-acceptance']
    files.extend(path for path in (home / '.t3/runtime').rglob('*') if path.is_file())
    return {str(path.relative_to(home)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in files}


if phase == 'prepare':
    # Explicit test setup outside Provisioning: a real local service, no Connect
    # identity, credentials, provider enrollment, or external reachability.
    base = home / '.t3'
    base.mkdir(exist_ok=True)
    (base / 'service.env').write_text('T3CODE_HOST=127.0.0.1\n')
    run('sudo', '-n', 'loginctl', 'enable-linger', str(os.getuid()))
    run('t3', 'service', 'install')
    # Bounded readiness wait; runtime creation follows systemd's active state.
    deadline = time.monotonic() + 60
    runtime = base / 'userdata/server-runtime.json'
    while not runtime.exists() and time.monotonic() < deadline:
        time.sleep(1)
    assert runtime.exists(), 'T3 service did not become ready in 60 seconds'
    secret = base / 'userdata/secrets/proteus-acceptance'
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_text('not-a-credential\n')
    # Recreate the previous Provisioning-owned npm installation/link.
    baseline = run(str(home / '.local/bin/mise'), 'config', 'get', '--global', 'tools.node')
    node = run(str(home / '.local/bin/mise'), 'where', 'node@' + baseline)
    run(node + '/bin/npm', 'install', '--global', '--no-audit', '--no-fund', 't3@latest',
        env={**environment, 'PATH': node + '/bin:' + environment['PATH']})
    command = home / '.local/bin/t3'
    command.unlink()
    command.symlink_to(Path(node) / 'bin/t3')
    record.write_text(json.dumps({'service': service(), 'files': snapshot()}))
    print('T3: seeded legacy npm link and dummy state beside a real unauthenticated local service.')
else:
    assert phase in ('fresh', 'repeated'), phase
    version = run('t3', '--version')
    binary = (home / '.local/bin/t3').resolve().read_bytes()
    assert binary[:4] == b'\x7fELF' and int.from_bytes(binary[18:20], 'little') == 183
    assert Path(shutil.which('t3', path=environment['PATH'])).resolve() == (home / '.local/bin/t3').resolve()
    with tempfile.TemporaryDirectory(prefix='proteus-t3-') as temporary:
        root = Path(temporary)
        poison = root / 'bin'
        poison.mkdir()
        node = poison / 'node'
        node.write_text('#!/bin/sh\necho unexpected-node-resolution >&2\nexit 97\n')
        node.chmod(0o755)
        for declaration, text in (('.nvmrc', '20.19.0'), ('.node-version', '22.16.0'),
                                  ('mise.toml', '[tools]\nnode = "99.99.99"\n')):
            project = root / declaration.removeprefix('.')
            project.mkdir()
            (project / declaration).write_text(text + '\n')
            env = {**environment, 'PATH': str(poison) + ':' + environment['PATH']}
            assert run('t3', '--version', env=env, cwd=project) == version
            assert run('bash', '--noprofile', '--norc', '-ic', 't3 --version', env=env, cwd=project) == version
            status = json.loads(run('t3', 'connect', 'status', '--json', env=env, cwd=project))
            assert status['authenticated'] is False, 'Acceptance must not enroll Connect'
    if phase == 'fresh':
        assert run('systemctl', '--user', 'show', 't3code.service', '--property=LoadState', '--value') == 'not-found'
    else:
        before = json.loads(record.read_text())
        assert service() == before['service'], 'Provisioning restarted or changed the service'
        assert snapshot() == before['files'], 'Provisioning changed runtime, unit, configuration, or dummy state'
        assert not list((home / '.local/share/mise/installs/node').glob('*/lib/node_modules/t3'))
        assert not list((home / '.local/share/mise/installs/node').glob('*/bin/t3'))
    print(f'T3 {phase} acceptance passed: {version}; ARM64, system PATH, Node independence, service preservation.')
