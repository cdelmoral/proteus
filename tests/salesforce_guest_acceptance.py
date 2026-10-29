"""Real Linux ARM64 Salesforce assertions in the existing Lima acceptance flow."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

home = Path.home()
phase = sys.argv[1]
record = home / '.cache/proteus/salesforce-acceptance.json'
mise = str(home / '.local/bin/mise')
environment = {'HOME': str(home), 'PATH': '/usr/local/bin:/usr/bin:/bin',
               'XDG_CONFIG_HOME': str(home / '.config'),
               'SF_USE_GENERIC_UNIX_KEYCHAIN': 'false', 'SF_DISABLE_TELEMETRY': 'false',
               'SF_AUTOUPDATE_DISABLE': 'false', 'SF_DISABLE_AUTOUPDATE': 'false'}


def run(*command, **kwargs):
    result = subprocess.run(command, capture_output=True, text=True, timeout=180, **kwargs)
    assert result.returncode == 0, (command, result.stdout, result.stderr)
    return result.stdout.strip()


if phase == 'prepare':
    # Dummy state in this disposable guest, never a real credential/login.
    files = {'.sf/config.json': '{"target-dev-hub":"acceptance-devhub"}\n',
             '.sfdx/key.json': '{"proteusAcceptance":"dummy-file-keychain"}\n',
             '.sf/proteus-acceptance-state': 'preserve-user-state\n'}
    for name, content in files.items():
        path = home / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    record.write_text(json.dumps({name: hashlib.sha256((home / name).read_bytes()).hexdigest()
                                 for name in files}))
    print('Seeded dummy Salesforce state; no Credential Enrollment.')
else:
    assert phase in ('fresh', 'repeated'), phase
    version = run('sf', '--version', env=environment)
    assert '@salesforce/cli/' in version and 'linux-arm64' in version, version
    bundled = home / '.local/share/proteus/salesforce-cli/current/bin/node'
    with bundled.open('rb') as binary:
        header = binary.read(20)
    assert header[:4] == b'\x7fELF' and int.from_bytes(header[18:20], 'little') == 183
    # Exercise a real user-manager subprocess without interactive startup files.
    service_version = run('systemd-run', '--user', '--wait', '--pipe', '--collect',
                          '/usr/bin/env', 'SF_DISABLE_TELEMETRY=false',
                          'SF_USE_GENERIC_UNIX_KEYCHAIN=false', 'SF_AUTOUPDATE_DISABLE=false',
                          'sf', '--version')
    assert service_version == version, service_version
    # Explicitly install a second runtime. Test actual installed Node entries
    # and a failing missing-runtime boundary; project declaration resolution is
    # covered by the Node-selection ticket, not reimplemented here.
    if phase == 'fresh':
        run(mise, 'install', 'node@22.16.0', env={**os.environ, 'MISE_YES': '1'})
    else:
        run(mise, 'where', 'node@22.16.0')
    baseline = run(mise, 'config', 'get', '--global', 'tools.node')
    with tempfile.TemporaryDirectory(prefix='proteus-salesforce-') as temporary:
        root = Path(temporary)
        missing_bin = root / 'missing-bin'
        missing_bin.mkdir()
        poison = missing_bin / 'node'
        poison.write_text('#!/bin/sh\necho missing-project-node >&2\nexit 97\n')
        poison.chmod(0o755)
        for declaration, selection in (('.nvmrc', baseline), ('.node-version', '22.16.0'),
                                       ('mise.toml', '99.99.99')):
            project = root / declaration.removeprefix('.')
            project.mkdir()
            (project / declaration).write_text(
                f'[tools]\nnode = "{selection}"\n' if declaration == 'mise.toml' else selection + '\n')
            node_bin = missing_bin if selection == '99.99.99' else Path(run(mise, 'where', 'node@' + selection)) / 'bin'
            env = {**environment, 'PATH': str(node_bin) + ':' + environment['PATH']}
            assert run('sf', '--version', env=env, cwd=project) == version
            assert run('bash', '--noprofile', '--norc', '-ic', 'sf --version', env=env, cwd=project) == version
            failure = subprocess.run(['sf', 'proteus-invalid-command', 'argument with spaces'],
                                     env=env, cwd=project, capture_output=True, text=True, timeout=60)
            assert failure.returncode != 0, failure.stdout
    if phase == 'repeated':
        for name, digest in json.loads(record.read_text()).items():
            assert hashlib.sha256((home / name).read_bytes()).hexdigest() == digest, name
        run(mise, 'where', 'node@22.16.0')
    print(f'Salesforce {phase} passed: {version}; ARM64, background PATH, Node independence, no enrollment.')
