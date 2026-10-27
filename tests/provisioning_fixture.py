"""Small local vendor/Ansible boundary shared by standalone tool tests."""
import functools
import http.server
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def temporary_guest(test):
    temporary = tempfile.TemporaryDirectory()
    test.addCleanup(temporary.cleanup)
    test.directory = Path(temporary.name)
    test.home = test.directory / 'guest'
    test.system = test.directory / 'system'
    (test.system / 'bin').mkdir(parents=True)


def serve_vendor(test, handler=QuietHandler):
    test.server = http.server.ThreadingHTTPServer(
        ('127.0.0.1', 0), functools.partial(handler, directory=str(test.vendor)))
    threading.Thread(target=test.server.serve_forever, daemon=True).start()
    test.addCleanup(test.server.server_close)
    test.addCleanup(test.server.shutdown)


def prepare_playbook(test, tool, replacements=()):
    tasks = test.directory / (tool + '.yml')
    source = (ROOT / 'provisioning/tasks' / tasks.name).read_text()
    for original, replacement in replacements:
        source = source.replace(original, replacement)
    tasks.write_text(source)
    # Relative imports resolve beside the copied task under test.
    shared = 'migrate_npm_tool.yml'
    (test.directory / shared).write_text((ROOT / 'provisioning/tasks' / shared).read_text())
    test.playbook = test.directory / 'playbook.yml'
    test.playbook.write_text(json.dumps([{
        'name': 'Exercise standalone tool Provisioning', 'hosts': 'all', 'gather_facts': False,
        'vars_files': [str(ROOT / 'provisioning/group_vars/all.yml')],
        'tasks': [{'ansible.builtin.import_tasks': str(tasks)}]}]))


def provision(test, **variables):
    # Inherit the controlled test PATH, but never the caller's T3 home.
    environment = {key: value for key, value in os.environ.items() if key != 'T3CODE_HOME'}
    extra_variables = {'proteus_dotfiles_source': str(ROOT / 'dotfiles'),
                       **test.variables, **variables}
    return subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local',
                           str(test.playbook), '-e', json.dumps(extra_variables)],
                          env=environment, capture_output=True, text=True, timeout=90)
