.PHONY: test integration

test:
	./tests/provision_test.sh
	./tests/preferences_test.sh
	./tests/javascript_toolchain_test.sh

integration:
	./tests/integration.sh
