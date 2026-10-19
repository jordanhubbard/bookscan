.PHONY: all deps run check smoke
PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

all: check

deps:
	python3 -m venv .venv
	.venv/bin/python -m pip install -e . pytest

run:
	$(PYTHON) -m bookscan

check:
	QT_QPA_PLATFORM=offscreen $(PYTHON) -m pytest -q

smoke:
	QT_QPA_PLATFORM=offscreen $(PYTHON) -m pytest -q tests/test_smoke.py
