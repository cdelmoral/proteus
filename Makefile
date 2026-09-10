.PHONY: static dotfiles-regression lima-acceptance

static:
	ansible-playbook --syntax-check --inventory localhost, provisioning/playbook.yml
	ansible-playbook --syntax-check --inventory localhost, tests/dotfiles_conflicts.yml
	ansible-lint --profile safety provisioning tests/dotfiles_conflicts.yml
	shellcheck provision tests/lima_acceptance.sh tests/dotfiles_conflicts.sh
	limactl validate vm/proteus.yaml

dotfiles-regression:
	./tests/dotfiles_conflicts.sh

lima-acceptance:
	./tests/lima_acceptance.sh
