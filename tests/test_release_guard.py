"""Exercise the production entrypoint/Ansible guard before a simulated baseline."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from provisioning_fixture import ROOT


@unittest.skipUnless(shutil.which('ansible-playbook'), 'Ansible is required')
class ReleaseGuardTest(unittest.TestCase):
    def setUp(self):
        import yaml
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.home = self.directory / 'guest'
        self.home.mkdir()
        self.repository = self.directory / 'repository'
        provisioning = self.repository / 'provisioning'
        provisioning.mkdir(parents=True)
        shutil.copy2(ROOT / 'provision', self.repository / 'provision')
        shutil.copy2(ROOT / 'provisioning/accept-release.sh', provisioning)
        self.version = self.repository / 'VERSION'
        self.version.write_text('1.0.0\n')
        self.marker = self.home / '.local/state/proteus/accepted-version'
        self.mutation = self.home / 'baseline-mutated'
        self.failure = self.home / 'fail-baseline'
        # Keep the actual production guard, ordering and always tag. Replace
        # only the Python/apt boundary; never bootstrap or mutate the host.
        play, = yaml.safe_load((ROOT / 'provisioning/playbook.yml').read_text())
        play['pre_tasks'] = play['pre_tasks'][:2]
        play['pre_tasks'][1] = {
            'name': 'Simulated Python bootstrap/baseline mutation',
            'ansible.builtin.raw': 'echo mutation >> "$HOME/baseline-mutated"; '
                                  'test ! -f "$HOME/fail-baseline"',
            'changed_when': True, 'tags': ['always']}
        play['tasks'] = []
        play.pop('handlers')
        self.playbook = provisioning / 'playbook.yml'
        self.playbook.write_text(yaml.safe_dump([play]))
        commands = self.directory / 'bin'
        commands.mkdir()
        self.ssh_config = self.directory / 'ssh.config'
        self.ssh_config.touch()
        (commands / 'limactl').write_text(
            '#!/bin/sh\nprintf "Running|localhost|%s\\n" "$FIXTURE_SSH_CONFIG"\n')
        # Real ./provision still resolves Lima metadata and invokes Ansible.
        # The transport is local and the guest HOME is disposable.
        (commands / 'ansible-playbook').write_text(
            '#!/bin/sh\nexec "$FIXTURE_ANSIBLE" -c local "$@"\n')
        for command in commands.iterdir():
            command.chmod(0o755)
        self.environment = {key: value for key, value in os.environ.items()
                            if key != 'T3CODE_HOME'}
        self.environment.update(HOME=str(self.home), PATH=str(commands) + ':' + os.environ['PATH'],
                                FIXTURE_ANSIBLE=shutil.which('ansible-playbook'),
                                FIXTURE_SSH_CONFIG=str(self.ssh_config),
                                ANSIBLE_NOCOLOR='1')

    def run_provision(self, direct=False):
        command = ([self.environment['FIXTURE_ANSIBLE'], '-i', 'localhost,', '-c', 'local',
                    str(self.playbook), '--tags', 'system'] if direct else
                   [str(self.repository / 'provision'), 'fixture'])
        return subprocess.run(command, env=self.environment, capture_output=True,
                              text=True, timeout=30)

    def seed(self, version):
        self.marker.parent.mkdir(parents=True, exist_ok=True)
        self.marker.write_text(version)

    def assert_rejected(self, installed, requested='1.0.0', direct=False):
        had_marker = self.marker.exists() or self.marker.is_symlink()
        before = {str(path.relative_to(self.home)): path.read_bytes()
                  for path in self.home.rglob('*') if path.is_file()}
        result = self.run_provision(direct=direct)
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0, output)
        for message in (installed, requested, 'rebuild', 'Credential Enrollment'):
            self.assertIn(message, output)
        self.assertFalse(self.mutation.exists(), output)
        # Ansible may create its own transport cache; all seeded guest data,
        # especially the accepted version, must remain byte for byte unchanged.
        for name, content in before.items():
            self.assertEqual((self.home / name).read_bytes(), content)
        self.assertEqual(self.marker.exists() or self.marker.is_symlink(), had_marker)

    def test_fresh_repeat_and_numeric_compatible_upgrades(self):
        for version in ('1.0.0', '1.0.0', '1.0.9', '1.0.10', '1.2.0', '1.10.0',
                        '1.999999999999999999999999999999.0'):
            with self.subTest(version=version):
                self.version.write_text(version + '\n')
                result = self.run_provision()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(self.marker.read_text(), version + '\n')
        self.assertEqual(len(self.mutation.read_text().splitlines()), 7)

    def test_fresh_guest_with_unrelated_tools_and_state_is_accepted(self):
        (self.home / '.claude').mkdir()
        (self.home / '.claude/credential').write_text('preserve')
        result = self.run_provision(direct=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.home / '.claude/credential').read_text(), 'preserve')

    def test_unversioned_proteus_footprint_requires_rebuild(self):
        footprint = self.home / '.local/share/proteus/mise/old'
        footprint.mkdir(parents=True)
        (footprint / 'mise').write_text('old Proteus installation')
        self.assert_rejected('<unversioned>')

    def test_incompatible_major_rejected_via_direct_tagged_playbook(self):
        self.seed('1.0.0\n')
        self.version.write_text('2.0.0\n')
        self.assert_rejected('1.0.0', '2.0.0', direct=True)

    def test_all_downgrades_rejected(self):
        for installed in ('1.0.1', '1.1.0', '2.0.0'):
            with self.subTest(installed=installed):
                self.seed(installed + '\n')
                self.assert_rejected(installed)

    def test_corrupt_marker_rejected(self):
        for installed in ('', 'garbage', '01.0.0', '1.0', '1.0.0-rc1',
                          '1.0.0\n\n', '1.0.0\n2.0.0', '<unversioned>', '1.0.\x000\n'):
            with self.subTest(installed=installed):
                self.seed(installed)
                self.assert_rejected('installed/accepted')

    def test_non_file_markers_rejected(self):
        self.marker.parent.mkdir(parents=True)
        self.marker.mkdir()
        self.assert_rejected('invalid marker')
        self.marker.rmdir()
        target = self.home / 'other-version'
        target.write_text('1.0.0\n')
        self.marker.symlink_to(target)
        self.assert_rejected('invalid marker')

    def test_invalid_repository_version_rejected_before_recording(self):
        for requested in ('', '01.0.0', 'v1.0.0', '1.0.0+build', '1.0.0\n\n',
                          '1.0.0; touch unsafe', '1.0.0\n2.0.0', '1.0.\x000\n'):
            with self.subTest(requested=requested):
                self.version.write_text(requested)
                self.assert_rejected('<unversioned>', 'Invalid repository VERSION')

    def test_failed_initial_run_and_failed_upgrade_can_retry_but_not_downgrade(self):
        self.failure.touch()
        self.assertNotEqual(self.run_provision().returncode, 0)
        self.assertEqual(self.marker.read_text(), '1.0.0\n')
        self.failure.unlink()
        self.assertEqual(self.run_provision().returncode, 0)
        self.version.write_text('1.1.0\n')
        self.failure.touch()
        self.assertNotEqual(self.run_provision().returncode, 0)
        self.assertEqual(self.marker.read_text(), '1.1.0\n')
        self.mutation.unlink()
        self.version.write_text('1.0.0\n')
        self.assert_rejected('1.1.0')
        self.version.write_text('1.1.0\n')
        self.failure.unlink()
        self.assertEqual(self.run_provision(direct=True).returncode, 0)
