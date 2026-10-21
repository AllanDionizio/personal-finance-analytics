.PHONY: setup data deps build test docs lint all dashboard dashboard-dev site \
	dashboard-pt dashboard-dev-pt real real-dashboard real-context

# Use the project's virtualenv when there is one, activated or not (CI
# installs into its own Python and has none)
ifneq ($(wildcard $(CURDIR)/.venv/bin/python),)
export VIRTUAL_ENV := $(CURDIR)/.venv
export PATH := $(CURDIR)/.venv/bin:$(PATH)
endif

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

# The site as GitHub Pages serves it: the dashboard at the root, the dbt docs
# (one self-contained page) under dbt-docs/. Needs `make build` first.
site: dashboard
	cd dbt && dbt docs generate --static
	rm -rf site && mkdir -p site/dbt-docs
	cp -r dashboards/build/. site/
	cp dbt/target/static_index.html site/dbt-docs/index.html

# The Portuguese dashboard: dashboards/pt holds translated pages and the
# sources that translate the marts' labels; they are laid over a copy of the
# project in $(PT_DIR), which shares node_modules. WAREHOUSE picks the file
# in data/; Evidence resolves it from the source folder, so the path is relative.
PT_DIR := .dashboards-pt
WAREHOUSE ?= warehouse.duckdb

dashboard-pt: dashboards/node_modules
	rm -rf $(PT_DIR) && mkdir -p $(PT_DIR)
	cd dashboards && cp -r .npmrc evidence.config.yaml package.json tailwind.config.cjs \
		components sources $(CURDIR)/$(PT_DIR)/
	cp -r dashboards/pt/. $(PT_DIR)/
	ln -s $(CURDIR)/dashboards/node_modules $(PT_DIR)/node_modules
	cd $(PT_DIR) && EVIDENCE_SOURCE__warehouse__filename=../../../data/$(WAREHOUSE) \
		npm run sources

dashboard-dev-pt: dashboard-pt
	cd $(PT_DIR) && npm run dev -- --host 127.0.0.1

# Real-data mode, on this machine only: the workbooks sit in data/raw and the
# warehouse in data/real.duckdb (both gitignored), and .env.real (gitignored,
# see .env.real.example) can map the placeholders to real names. Never run
# `make site` against it: the public site is built from synthetic data.
REAL_DB := $(CURDIR)/data/real.duckdb
LOAD_REAL_ENV := set -a; if [ -f .env.real ]; then . ./.env.real; fi; set +a;

real: deps
	python -m ingestion.extract_sheets --xlsx-dir data/raw --db $(REAL_DB)
	$(LOAD_REAL_ENV) cd dbt && DUCKDB_PATH=$(REAL_DB) NEW_MONEY_SOURCE=savings dbt build

real-dashboard:
	$(MAKE) dashboard-dev-pt WAREHOUSE=real.duckdb

# A Markdown summary of the real finances, for a chat assistant's context
real-context:
	python -m reports.household_context --db $(REAL_DB) \
		--profile data/personal/perfil.md --out data/personal/contexto.md

# From a fresh clone to a built warehouse and dashboard
all: data build dashboard

docs:
	cd dbt && dbt docs generate && dbt docs serve

lint:
	ruff check . && ruff format --check .
	DUCKDB_PATH=$(CURDIR)/data/warehouse.duckdb sqlfluff lint dbt/models
