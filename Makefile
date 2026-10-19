# Developer entry points for the retained BookScan implementation.
IMPL := components/legacy-project-wrapper/implementation
PYTHON ?= $(if $(wildcard .venv/bin/python),$(abspath .venv/bin/python),python3)
.PHONY: all deps deps-tools run check smoke verify install
all: check

deps: deps-tools
	python3 -m venv .venv
	.venv/bin/python -m pip install -e $(IMPL) pytest

deps-tools:
	$(MAKE) -C $(IMPL) deps-tools

run:
	cd $(IMPL) && $(PYTHON) -m bookscan

check:
	$(MAKE) -C $(IMPL) check PYTHON=$(PYTHON)

smoke:
	$(MAKE) -C $(IMPL) smoke PYTHON=$(PYTHON)

verify:
	litai verify

install:
	$(PYTHON) -m bookscan --install-desktop
