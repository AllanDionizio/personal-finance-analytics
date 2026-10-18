.PHONY: setup seed build test docs lint

export DBT_PROFILES_DIR := $(CURDIR)/dbt

setup:
	pip install -e ".[dev]"
	pre-commit install

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
