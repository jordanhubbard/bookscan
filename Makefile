.PHONY: all deps deps-tools run check smoke
CODEGRAPH_VERSION := 1.6.2
NPM_PREFIX ?= $(HOME)/.local
PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

all: check

deps: deps-tools
	python3 -m venv .venv
	.venv/bin/python -m pip install -e . pytest

deps-tools:
	npm install --global --prefix "$(NPM_PREFIX)" @colbymchenry/codegraph@$(CODEGRAPH_VERSION)

run:
	$(PYTHON) -m bookscan

check:
	QT_QPA_PLATFORM=offscreen $(PYTHON) -m pytest -q

smoke:
	QT_QPA_PLATFORM=offscreen $(PYTHON) -m pytest -q tests/test_smoke.py
