.PHONY: test integration

test:
	./tests/provision_test.sh

integration:
	./tests/integration.sh
