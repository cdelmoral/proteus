.PHONY: test static integration ci-integration lima-acceptance

test:
	./tests/provision_test.sh
	./tests/preferences_test.sh
	./tests/javascript_toolchain_test.sh
	./tests/mise_home_test.sh
	./tests/ci_test.sh
	./tests/lima_acceptance_test.sh

static:
	ansible-playbook --syntax-check --inventory localhost, provisioning/playbook.yml
	ansible-lint --profile safety provisioning
	yamllint .github provisioning vm tests/preferences_test.yml
	bash -n provision tests/*.sh
	shellcheck provision tests/*.sh
	actionlint -ignore 'label "ubuntu-26.04-arm" is unknown'
	limactl validate vm/proteus.yaml

integration:
	./tests/integration.sh

ci-integration:
	./tests/ci_integration.sh

lima-acceptance:
	./tests/lima_acceptance.sh
