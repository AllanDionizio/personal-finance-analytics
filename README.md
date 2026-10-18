# personal-finance-analytics

![CI](https://github.com/AllanDionizio/personal-finance-analytics/actions/workflows/ci.yml/badge.svg)
![dbt](https://img.shields.io/badge/dbt-1.x-orange)
![Python](https://img.shields.io/badge/python-3.11-blue)

> An end-to-end analytics engineering project that turns six years of household finance spreadsheets into a tested star schema and a self-serve dashboard.

🚧 **Work in progress.** Ingestion and the synthetic dataset are done. The dbt models and dashboard are being built; see [Roadmap](#roadmap).

## Why this project

For six years, a couple tracked every transaction in yearly Google Sheets workbooks. The sheets work for data entry but can't answer cross-year questions: how fixed costs evolved, how much is still owed in installments, how the investment portfolio grew. Half of the meaning isn't even in the cells: **who spent** and **which card was used** are encoded as cell background colors.

This project extracts that data, colors included, into DuckDB and models it with dbt so those questions become simple queries.

## Architecture

```mermaid
flowchart LR
    A[Source: yearly XLSX exports] --> B[Ingestion: Python + openpyxl]
    B --> C[(Warehouse: DuckDB)]
    C --> D[dbt: staging → intermediate → marts]
    D --> E[BI: Evidence]
    F[GitHub Actions] -.CI.-> B
    F -.-> D
```

## Synthetic data

The real workbooks hold a household's finances, so they never leave the owners' machine. The repo instead ships a generator (`synthetic/`) that writes six yearly workbooks with the same layout, so the ingestion runs on them unchanged:

- credits and debits side by side on the same sheet rows, with a different column layout in 2021
- owner and card encoded as cell colors, with the same color stored as `rgb` in some cells and as a `theme` index in others
- card purchases split into `(k/N)` installments that cross year boundaries
- a portfolio sheet that stacks one block per snapshot, repeats the whole history in every year's file and gains columns over time
- hand-typed noise: case and whitespace drift, legacy categories, blank macro-categories, stray highlight colors

Output is deterministic for a given seed, so tests and CI always see the same data.

## Data model

Planned star schema (full design in [`docs/data-model.md`](docs/data-model.md)):

| Model | Type | Grain | Description |
| --- | --- | --- | --- |
| `fct_transactions` | Fact | One row per transaction | Credits and debits, with installment and effective-amount flags |
| `fct_portfolio_snapshots` | Fact | One row per asset per reference date | Investment portfolio history |
| `dim_date` | Dimension | One row per day | Generated calendar |
| `dim_category` | Dimension | One row per category | Category, macro-category (fixed / variable), type |
| `dim_owner` | Dimension | One row per owner | Derived from cell colors |
| `dim_payment_method` | Dimension | One row per payment method | Derived from cell colors |

## Data quality

- Python unit tests for every ingestion library (color resolution, installment parsing, snapshot block detection)
- End-to-end tests that generate the synthetic workbooks, run the ingestion and check what lands in DuckDB
- Known bugs are pinned as strict `xfail` tests, so the fix has to flip them to passing
- Planned: generic and custom dbt tests on every key, source freshness, `dbt build` on every pull request

## Tech stack

| Layer | Tool | Why this choice |
| --- | --- | --- |
| Ingestion | Python + openpyxl | Reads cell fill colors, which carry business meaning (owner, card) |
| Warehouse | DuckDB | Zero-infra, file-based, runs the same locally and in CI |
| Transformation | dbt (`dbt-duckdb`) | Tested, documented, version-controlled SQL |
| BI | Evidence | Dashboards as code, versioned next to the models |
| CI | GitHub Actions | Lint, tests and `dbt build` on every pull request |

## How to run

```bash
git clone https://github.com/AllanDionizio/personal-finance-analytics.git
cd personal-finance-analytics
python -m venv .venv && source .venv/bin/activate
make setup
```

Generate the synthetic workbooks and load them into DuckDB:

```bash
make data   # synthetic XLSX → data/synthetic/ → raw.* in data/warehouse.duckdb
```

No credentials or real data needed. The ingestion is idempotent: re-running on the same files reloads by `source_file` without duplicating rows. Unrecognized cell colors are logged with counts instead of failing the run.

## Design decisions & trade-offs

- **Decision:** keep the raw layer literal (installment suffixes and raw color codes untouched). **Why:** parsing rules can change and be replayed in dbt without re-reading the workbooks. **Trade-off:** the raw tables are not directly queryable for analysis.
- **Decision:** resolve both `rgb` and `theme` color references. **Why:** Google Sheets exports the same visible color either as a hex value or as a theme index, depending on how it was applied. **Trade-off:** the resolver depends on parsing `xl/theme/theme1.xml` inside each workbook.
- **Decision:** detect the debit-side layout from the header row instead of fixed positions. **Why:** a column was added in 2022, so 2021 workbooks have a different layout. **Trade-off:** the header detection has to be tested against both layouts.

## Roadmap

- [x] Data model design
- [x] Ingestion libraries with unit tests
- [x] Ingestion CLI: XLSX → `raw.*` in DuckDB
- [x] Repository standards: CI, pre-commit, lint
- [x] Synthetic dataset with the same structure as the real workbooks
- [ ] dbt staging, intermediate and marts
- [ ] dbt tests and published dbt docs
- [ ] Evidence dashboard, deployed on the synthetic data

## Repository structure

```
├── .github/workflows/   # CI
├── ingestion/           # Python extract & load
├── synthetic/           # synthetic workbook generator
├── dbt/                 # models, tests, macros, seeds
├── tests/               # Python unit tests
└── docs/                # data model design
```

---

Built by [Allan Dionizio](https://github.com/AllanDionizio) · [LinkedIn](https://www.linkedin.com/in/allandionizio/)
