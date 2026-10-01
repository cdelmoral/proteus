.PHONY: static lima-acceptance

static:
	ansible-playbook --syntax-check --inventory localhost, provisioning/playbook.yml
	ansible-lint --profile safety provisioning
	shellcheck configure provision tests/lima_acceptance.sh
	limactl validate vm/proteus.yaml

lima-acceptance:
	./tests/lima_acceptance.sh
