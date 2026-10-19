.PHONY: setup data deps build test docs lint all

export DBT_PROFILES_DIR := $(CURDIR)/dbt

setup:
	pip install -e ".[dev]"
	pre-commit install

# Synthetic workbooks → raw.* in DuckDB (no real data needed)
data:
	python -m synthetic.generate --out data/synthetic
	python -m ingestion.extract_sheets --xlsx-dir data/synthetic --db data/warehouse.duckdb

deps:
	cd dbt && dbt deps

# Seeds, models, unit tests and data tests, in DAG order
build: deps
	cd dbt && dbt build
	cd dbt && dbt source freshness

test:
	pytest -q
	cd dbt && dbt test

# From a fresh clone to a built warehouse
all: data build

docs:
	cd dbt && dbt docs generate && dbt docs serve

lint:
	ruff check . && ruff format --check .
	DUCKDB_PATH=$(CURDIR)/data/warehouse.duckdb sqlfluff lint dbt/models
