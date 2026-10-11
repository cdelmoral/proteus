.PHONY: static test lima-acceptance

static:
	ansible-playbook --syntax-check --inventory localhost, provisioning/playbook.yml
	ansible-lint --profile safety provisioning
	shellcheck configure enroll provision lib/config.sh dotfiles/home/.local/bin/gh dotfiles/home/.local/bin/proteus-enroll-github dotfiles/home/.local/bin/proteus-git-credential-github dotfiles/home/.local/lib/proteus/credentials.sh tests/lima_acceptance.sh
	shellcheck --shell=bash dotfiles/home/.bashrc dotfiles/home/.local/lib/proteus/credentials.sh
	limactl validate vm/proteus.yaml

test:
	python3 -B -m unittest discover -s tests -p 'test_*.py'

lima-acceptance:
	./tests/lima_acceptance.sh
