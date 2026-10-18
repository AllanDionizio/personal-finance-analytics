.PHONY: setup data seed build test docs lint

export DBT_PROFILES_DIR := $(CURDIR)/dbt

setup:
	pip install -e ".[dev]"
	pre-commit install

# Synthetic workbooks → raw.* in DuckDB (no real data needed)
data:
	python -m synthetic.generate --out data/synthetic
	python -m ingestion.extract_sheets --xlsx-dir data/synthetic --db data/warehouse.duckdb

seed:
	cd dbt && dbt deps && dbt seed

build:
	cd dbt && dbt build

test:
	cd dbt && dbt test
	pytest -q

docs:
	cd dbt && dbt docs generate && dbt docs serve

lint:
	ruff check . && ruff format --check .
	sqlfluff lint dbt/models
