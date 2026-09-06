.PHONY: test integration lima-acceptance

test:
	./tests/provision_test.sh
	./tests/preferences_test.sh
	./tests/javascript_toolchain_test.sh
	./tests/lima_acceptance_test.sh

integration:
	./tests/integration.sh

lima-acceptance:
	./tests/lima_acceptance.sh
