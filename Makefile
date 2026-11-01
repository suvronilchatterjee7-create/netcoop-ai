PY ?= python
VENV ?= .venv
ifeq ($(OS),Windows_NT)
  BIN := $(VENV)/Scripts
else
  BIN := $(VENV)/bin
endif

.PHONY: setup generate profile schemas calibrate fit run demo serve test eval quick-eval lint typecheck clean

setup:
	$(PY) -m venv $(VENV)
	$(BIN)/python -m pip install -U pip
	$(BIN)/python -m pip install -e ".[dev]"

generate:
	$(BIN)/netcoop generate

profile:
	$(BIN)/netcoop profile

schemas:
	$(BIN)/netcoop schemas

calibrate:
	$(BIN)/netcoop calibrate

serve:
	$(BIN)/netcoop serve

demo:
	$(BIN)/netcoop demo --step

run:
	$(BIN)/netcoop run $(INPUT)

test:
	$(BIN)/python -m pytest --cov=netcoop --cov-report=term

fit:
	$(BIN)/netcoop fit

eval:
	$(BIN)/netcoop eval

quick-eval:
	$(BIN)/netcoop eval --quick

lint:
	$(BIN)/ruff check netcoop tests scripts

typecheck:
	$(BIN)/mypy netcoop

clean:
	rm -rf runs .pytest_cache .mypy_cache .ruff_cache
