# All Python runs as `.venv/bin/python -m ...` because console-script shebangs break when the repo
# path contains spaces. Recipes quote nothing relative, so a spaced checkout path is safe.
PY := .venv/bin/python

.PHONY: help setup dataset api ui test lint benchmark demo keys audit-verify secrets licenses

help:
	@echo "setup      Create .venv and install Python and frontend dependencies"
	@echo "dataset    Regenerate the synthetic demo dataset"
	@echo "api        Run the API on http://localhost:8000"
	@echo "ui         Run the UI on http://localhost:5173"
	@echo "test       Lint and run the test suite"
	@echo "benchmark  Score the pipeline against ground truth (writes docs/benchmark_results.*)"
	@echo "demo       Run the API and UI together"
	@echo "keys       Check configured LLM providers"
	@echo "secrets    Scan the repo and git history for secrets"
	@echo "licenses   Regenerate THIRD_PARTY.md from installed package metadata"

setup:
	python3.12 -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements.txt
	cd frontend && npm install

dataset:
	$(PY) -m scripts.generate_dataset

api:
	$(PY) -m uvicorn backend.app:app --host 127.0.0.1 --port 8000

ui:
	cd frontend && npm run dev

lint:
	$(PY) -m ruff check .

test: lint
	$(PY) -m pytest

benchmark:
	$(PY) -m scripts.run_benchmark

demo:
	$(MAKE) -j2 api ui

keys:
	$(PY) -m scripts.check_keys

audit-verify:
	$(PY) -m scripts.verify_audit_chain

secrets:
	bash scripts/secret_scan.sh

licenses:
	$(PY) -m scripts.gen_third_party
