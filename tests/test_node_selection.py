"""Real mise resolution with isolated installations; no runtime downloads.

Set PROTEUS_TEST_MISE to the pinned mise executable. Node fixtures report their
identity; real Node/pnpm execution is covered by the Lima acceptance flow.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MISE = os.environ.get('PROTEUS_TEST_MISE')


@unittest.skipUnless(MISE, 'Set PROTEUS_TEST_MISE to mise 2026.9.1')
class NodeSelectionTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.env = {
            'HOME': str(self.home), 'PATH': '/usr/bin:/bin',
            'MISE_CONFIG_DIR': str(self.home / '.config/mise'),
            'MISE_DATA_DIR': str(self.home / '.local/share/mise'),
            'MISE_CACHE_DIR': str(self.home / '.cache/mise'),
            'MISE_STATE_DIR': str(self.home / '.local/state/mise'),
        }
        config = self.home / '.config/mise'
        (config / 'conf.d').mkdir(parents=True)
        shutil.copy(ROOT / 'dotfiles/home/.config/mise/conf.d/proteus.toml', config / 'conf.d')
        (config / 'config.toml').write_text('[tools]\nnode = "22.14.0"\n')
        for version in ['22.14.0', '20.19.0']:
            binary = self.home / f'.local/share/mise/installs/node/{version}/bin/node'
            binary.parent.mkdir(parents=True)
            binary.write_text(f'#!/bin/sh\nprintf "v{version}\\n"\n')
            binary.chmod(0o755)
        self.assertEqual(self.run_mise('--version').stdout.split()[0], '2026.9.1')
        self.assertEqual(self.run_mise('reshim').returncode, 0)

    def run_mise(self, *args, cwd=None):
        return subprocess.run([MISE, *args], cwd=cwd or self.home,
                              env=self.env, capture_output=True, text=True, timeout=20)

    def shell(self, script):
        # Use the exact activation command from Managed Dotfiles, with paths
        # supplied by this isolated test instead of sourcing unrelated apps.
        activation = next(line for line in (ROOT / 'dotfiles/home/.bashrc').read_text().splitlines()
                          if 'mise" activate' in line)
        binary = self.home / '.local/bin/mise'
        binary.parent.mkdir(parents=True, exist_ok=True)
        if not binary.exists():
            binary.symlink_to(MISE)
        return subprocess.run(['bash', '--noprofile', '--norc', '-ic', activation + '\n' + script],
                              cwd=self.home, env=self.env, capture_output=True, text=True, timeout=20)

    def test_declarations_directory_switching_and_default(self):
        for filename, content in [('.nvmrc', 'v20.19.0\n'), ('.node-version', '20.19.0\n'),
                                  ('mise.toml', '[tools]\nnode = "20.19.0"\n')]:
            project = self.home / filename.replace('.', '')
            project.mkdir()
            declaration = project / filename
            declaration.write_text(content)
            if filename == 'mise.toml':
                self.assertEqual(self.run_mise('trust', str(declaration)).returncode, 0)
            result = self.shell(f'node -v; cd "{project}"; node -v; cd "$HOME"; node -v')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.splitlines(), ['v22.14.0', 'v20.19.0', 'v22.14.0'])
        self.assertEqual((self.home / '.config/mise/config.toml').read_text(), '[tools]\nnode = "22.14.0"\n')

    def test_missing_version_rejects_fallback_and_does_not_install(self):
        project = self.home / 'missing'
        project.mkdir()
        (project / '.nvmrc').write_text('18.20.8\n')
        # Even an available system Node must not be selected on failure.
        fallback = self.home / 'fallback'
        fallback.mkdir()
        (fallback / 'node').write_text('#!/bin/sh\necho wrong-fallback\n')
        (fallback / 'node').chmod(0o755)
        self.env['PATH'] = str(fallback) + ':/usr/bin:/bin'
        result = self.shell(f'node -v; cd "{project}"; node -v')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('wrong-fallback', result.stdout)
        self.assertIn('mise install', result.stderr)
        self.assertFalse((self.home / '.local/share/mise/installs/node/18.20.8').exists())
