.PHONY: setup data deps build test docs lint all dashboard dashboard-dev

export DBT_PROFILES_DIR := $(CURDIR)/dbt
# Evidence sends anonymous usage stats unless told not to
export SEND_ANONYMOUS_USAGE_STATS := no

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

# Evidence: install once per lockfile change
dashboards/node_modules: dashboards/package-lock.json
	cd dashboards && npm ci
	touch dashboards/node_modules

# Extract the marts into Evidence's cache and build the static site
dashboard: dashboards/node_modules
	cd dashboards && npm run sources && npm run build:strict

# Live-reloading dashboard; Evidence prints the local URL
dashboard-dev: dashboards/node_modules
	cd dashboards && npm run sources && npm run dev

# From a fresh clone to a built warehouse and dashboard
all: data build dashboard

docs:
	cd dbt && dbt docs generate && dbt docs serve

lint:
	ruff check . && ruff format --check .
	DUCKDB_PATH=$(CURDIR)/data/warehouse.duckdb sqlfluff lint dbt/models
