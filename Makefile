.PHONY: static test lima-acceptance

static:
	python3 -B -c 'import ast; from pathlib import Path; [ast.parse(p.read_text(), filename=str(p)) for p in [Path("aws-setup"), Path("dotfiles/home/.local/bin/proteus-enroll-aws"), *Path("lib").glob("*.py"), *Path("tests").glob("*.py")]]'
	ansible-playbook --syntax-check --inventory localhost, provisioning/playbook.yml
	ansible-lint --profile safety provisioning
	shellcheck provisioning/accept-release.sh configure enroll provision lib/config.sh dotfiles/home/.local/bin/gh dotfiles/home/.local/bin/proteus-capture-browser-url dotfiles/home/.local/bin/proteus-enroll-github dotfiles/home/.local/bin/proteus-enroll-twg dotfiles/home/.local/bin/proteus-git-credential-github dotfiles/home/.local/bin/sf dotfiles/home/.local/bin/opencode dotfiles/home/.local/lib/proteus/credentials.sh tests/lima_acceptance.sh tests/lima_opencode.sh
	shellcheck dotfiles/home/.local/bin/proteus-project-exec
	shellcheck --shell=sh dotfiles/home/.local/lib/proteus/project-env.sh
	shellcheck --shell=bash dotfiles/home/.bashrc dotfiles/home/.local/lib/proteus/credentials.sh
	limactl validate vm/proteus.yaml

test:
	python3 -B -m unittest discover -s tests -p 'test_*.py'

lima-acceptance:
	./tests/lima_acceptance.sh
