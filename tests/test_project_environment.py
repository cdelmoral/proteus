"""Provider boundary regressions; these are not real T3 acceptance evidence."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from provisioning_fixture import ROOT, prepare_playbook, provision, temporary_guest
from t3_node_probe import VERSIONS, probe, verify


@unittest.skipUnless(shutil.which('ansible-playbook'), 'Ansible is required')
class ProjectEnvironmentProvisioningTest(unittest.TestCase):
    def setUp(self):
        temporary_guest(self)
        (self.system / 'profile.d').mkdir()
        prepare_playbook(self, 'dotfiles')
        tasks = self.directory / 'dotfiles.yml'
        source = tasks.read_text().split('# System defaults apply', 1)[1]
        tasks.write_text('---\n# System defaults apply' + source.replace('/etc/', str(self.system) + '/')
                         .replace('become: true', 'become: false'))
        self.variables = {'ansible_facts': {'user_dir': str(self.home)},
                          'ansible_python_interpreter': os.sys.executable}

    def test_repeat_preserves_other_codex_settings_and_installs_command_policy(self):
        (self.system / 'codex').mkdir()
        config = self.system / 'codex/config.toml'
        config.write_text('model = "preserve-model"\n[other]\nsetting = "preserve"\n')
        for _ in range(2):
            result = provision(self)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            data = tomllib.loads(config.read_text())
            self.assertEqual(data['model'], 'preserve-model')
            self.assertEqual(data['other']['setting'], 'preserve')
            environment = data['shell_environment_policy']['set']
            self.assertEqual(environment['BASH_ENV'], str(self.home / '.local/lib/proteus/project-env.sh'))
            self.assertTrue(environment['PATH'].startswith(str(self.home / '.local/bin') + ':'))
        # Exercise the installed login-shell fragment with a private runtime
        # PATH. It must retain unrelated search locations after managed shims.
        destination = self.home / '.local/lib/proteus/project-env.sh'
        destination.parent.mkdir(parents=True)
        shutil.copy(ROOT / 'dotfiles/home/.local/lib/proteus/project-env.sh', destination)
        result = subprocess.run(['/bin/sh', '-c', '. "$1"; printf "%s" "$PATH"',
                                 'sh', str(self.system / 'profile.d/proteus-project.sh')],
                                env={'HOME': str(self.home), 'PATH': '/private/node/bin:/custom/bin'},
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f'{self.home}/.local/bin:{self.home}/.local/share/mise/shims:/private/node/bin:/custom/bin')

    def test_existing_command_policy_conflict_fails_without_overwriting_configuration(self):
        (self.system / 'codex').mkdir()
        config = self.system / 'codex/config.toml'
        original = '[shell_environment_policy.set]\nCUSTOM = "preserve"\n'
        config.write_text(original)
        result = provision(self)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(config.read_text(), original)


@unittest.skipUnless(shutil.which('node'), 'Node is required to exercise the OpenCode hook')
class OpenCodeEnvironmentTest(unittest.TestCase):
    def test_hook_overrides_inherited_and_per_command_paths_without_changing_parent(self):
        plugin = ROOT / 'dotfiles/home/.config/opencode/plugins/proteus-project-env.js'
        script = '''
import assert from 'node:assert/strict';
import {homedir} from 'node:os';
const {ProteusProjectEnvironment} = await import(process.argv[1]);
const original = process.env.PATH;
const hooks = await ProteusProjectEnvironment();
for (const path of [undefined, '/provider/private/node/bin:/custom/bin']) {
  const output = {env: path === undefined ? {} : {PATH: path}};
  await hooks['shell.env']({cwd: '/project'}, output);
  assert.equal(output.env.PATH, `${homedir()}/.local/bin:${homedir()}/.local/share/mise/shims:${path ?? original}`);
}
assert.equal(process.env.PATH, original);
'''
        result = subprocess.run(['node', '--input-type=module', '-e', script, str(plugin)],
                                text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)


class T3EvidenceTest(unittest.TestCase):
    def test_component_results_cannot_replace_missing_provider_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'baseline').write_text('24.20.0')
            with self.assertRaisesRegex(AssertionError, 'Missing actual T3 claude probe'):
                verify(root)
            (root / 'claude.json').write_text(json.dumps({'passed': True, 'provider': 'claude',
                                                       'versions': {'nvmrc': 'v24.20.0'}}))
            with self.assertRaises(AssertionError):
                verify(root)

    def test_agent_probe_rejects_private_runtime_and_removes_stale_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'baseline').write_text('24.20.0')
            for name in VERSIONS:
                (root / name).mkdir()
            private = root / 'private-runtime'
            private.mkdir()
            (private / 'node').write_text('#!/bin/sh\necho v24.20.0\n')
            (private / 'node').chmod(0o755)
            evidence = root / 'codex.json'
            evidence.write_text('{"passed": true}')
            # Satisfy only the helper-file prerequisite. The real subprocesses
            # inherit the contaminated agent environment and must be rejected.
            with patch('t3_node_probe.Path.is_file', return_value=True), patch.dict(
                    os.environ, {'PATH': str(private) + ':/usr/bin:/bin'}):
                with self.assertRaises(AssertionError):
                    probe(root, 'codex')
            self.assertFalse(evidence.exists())
