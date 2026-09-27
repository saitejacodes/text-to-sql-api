.PHONY: install test lint demo serve eval-all report

install:
	uv venv --python 3.12 && uv pip install -e ".[dev]"

test:
	.venv/bin/pytest -q

lint:
	.venv/bin/ruff check src tests && .venv/bin/ruff format --check src tests

demo:
	python scripts/make_demo_db.py

serve: demo
	.venv/bin/t2sql serve

# Full BIRD mini-dev ablation (see docs/EVALUATION.md). Resumable; cached LLM calls are free.
DATA ?= data/bird/mini_dev_sqlite.json
DBS  ?= data/bird/dev_databases
eval-all:
	for p in bare mschema values full; do .venv/bin/t2sql eval --data $(DATA) --db-root $(DBS) --preset $$p; done

report:
	.venv/bin/t2sql report runs
