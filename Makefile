# Developer and per-user installation entry points for retained BookScan.
IMPL := components/legacy-project-wrapper/implementation
PYTHON3 ?= python3
PYTHON ?= $(abspath .venv/bin/python)
APP_VENV ?= $(HOME)/.local/share/bookscan/venv
.PHONY: all deps deps-tools build run check smoke verify install
all: check

# Recreate disposable tooling so removed/upgraded interpreters cannot strand it.
deps:
	$(PYTHON3) -m venv --clear .venv
	$(PYTHON) -m pip install -e $(IMPL) pytest build

.venv/bin/python:
	$(MAKE) deps

deps-tools:
	$(MAKE) -C $(IMPL) deps-tools

build: .venv/bin/python
	mkdir -p _build/dist
	rm -f _build/dist/bookscan-*.whl _build/dist/bookscan-*.tar.gz
	$(PYTHON) -m build $(IMPL) --outdir $(abspath _build/dist)

run: .venv/bin/python
	$(PYTHON) -m bookscan

check: .venv/bin/python
	$(MAKE) -C $(IMPL) check PYTHON=$(PYTHON)

smoke: .venv/bin/python
	$(MAKE) -C $(IMPL) smoke PYTHON=$(PYTHON)

verify:
	litai verify

# Install a wheel independently of the checkout and developer environment.
install: build
	$(PYTHON3) -m venv --clear "$(APP_VENV)"
	"$(APP_VENV)/bin/python" -m pip install _build/dist/bookscan-*.whl
	"$(APP_VENV)/bin/python" -m pip check
	"$(APP_VENV)/bin/python" -m bookscan --install-desktop
