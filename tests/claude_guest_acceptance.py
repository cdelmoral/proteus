"""Claude assertions inside the disposable guest, invoked by lima_acceptance.sh."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

home = Path.home()
phase = sys.argv[1]
record = home / '.cache/proteus/claude-acceptance.json'


def run(*command, **kwargs):
    result = subprocess.run(command, capture_output=True, text=True, timeout=180, **kwargs)
    assert result.returncode == 0, (command, result.stdout, result.stderr)
    return result.stdout.strip()


if phase == 'prepare':
    # This guest was created by the acceptance flow. These are dummy local
    # files, never real enrollment or copied host credentials.
    files = {
        '.claude/.credentials.json': '{"proteusAcceptance": "not-a-credential"}\n',
        '.claude/projects/proteus-acceptance/history': 'preserve-history\n',
    }
    for name, content in files.items():
        path = home / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    settings = home / '.claude/settings.json'
    data = json.loads(settings.read_text())
    data.setdefault('env', {})['PROTEUS_ACCEPTANCE_PRESERVED'] = 'yes'
    settings.write_text(json.dumps(data))
    config = home / '.claude.json'
    data = json.loads(config.read_text()) if config.exists() else {}
    data['proteusAcceptance'] = 'preserve-enrollment-state'
    config.write_text(json.dumps(data))
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps({name: hashlib.sha256((home / name).read_bytes()).hexdigest()
                                  for name in files}))
    # Recreate the previous Provisioning method using the real vendor npm
    # package. The second Provisioning must remove it without touching state.
    baseline = run(str(home / '.local/bin/mise'), 'config', 'get', '--global', 'tools.node')
    node = run(str(home / '.local/bin/mise'), 'where', 'node@' + baseline)
    environment = {**os.environ, 'PATH': node + '/bin:/usr/bin:/bin'}
    run(node + '/bin/npm', 'install', '--global', '--no-audit', '--no-fund',
        '@anthropic-ai/claude-code@latest', env=environment)
    command = home / '.local/bin/claude'
    command.unlink()
    command.symlink_to(Path(node) / 'bin/claude')
    print('Seeded obsolete npm installation and dummy user state; no Credential Enrollment.')
else:
    assert phase in ('fresh', 'repeated'), phase
    environment = {'HOME': str(home), 'PATH': '/usr/local/bin:/usr/bin:/bin',
                   'XDG_CONFIG_HOME': str(home / '.config')}
    version = run('claude', '--version', env=environment)
    assert 'Claude Code' in version, version
    assert Path(shutil.which('claude', path=environment['PATH'])).resolve() == (home / '.local/bin/claude').resolve()
    # Confirm the actual artifact's ELF architecture as well as launching it.
    binary = (home / '.local/bin/claude').resolve().read_bytes()
    assert binary[:4] == b'\x7fELF' and int.from_bytes(binary[18:20], 'little') == 183
    marketplaces = json.loads(run('claude', 'plugin', 'marketplace', 'list', '--json', env=environment))
    assert any(item['name'] == 'claude-plugins-official' for item in marketplaces)
    plugins = json.loads(run('claude', 'plugin', 'list', '--json', env=environment))
    assert any(item['id'] == 'mattpocock-skills@claude-plugins-official' for item in plugins), plugins
    policy = json.loads(Path('/etc/claude-code/managed-settings.json').read_text())
    assert policy['attribution'] == {'commit': '', 'pr': ''}
    assert policy['env']['DISABLE_AUTOUPDATER'] == '1'
    # Tool launches must not resolve Node, with both installed-looking and
    # missing project declarations. Full mise selection is a separate ticket.
    with tempfile.TemporaryDirectory(prefix='proteus-claude-') as temporary:
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
            assert run('claude', '--version', env=env, cwd=project) == version
            assert run('bash', '--noprofile', '--norc', '-ic', 'claude --version', env=env, cwd=project) == version
            status = subprocess.run(['claude', 'auth', 'status'], env=env, cwd=project,
                                    capture_output=True, text=True, timeout=30)
            assert status.returncode == 1, (status.stdout, status.stderr)
            assert json.loads(status.stdout)['loggedIn'] is False, status.stdout
    if phase == 'repeated':
        for name, digest in json.loads(record.read_text()).items():
            assert hashlib.sha256((home / name).read_bytes()).hexdigest() == digest, name
        assert json.loads((home / '.claude/settings.json').read_text())['env']['PROTEUS_ACCEPTANCE_PRESERVED'] == 'yes'
        assert json.loads((home / '.claude.json').read_text())['proteusAcceptance'] == 'preserve-enrollment-state'
        assert not list((home / '.local/share/mise/installs/node').glob('*/lib/node_modules/@anthropic-ai/claude-code'))
        assert not list((home / '.local/share/mise/installs/node').glob('*/bin/claude'))
    print(f'Claude {phase} acceptance passed: {version}; ARM64, system PATH, skills, auth status, Node independence.')
