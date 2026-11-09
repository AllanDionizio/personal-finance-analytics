# 1. Ship synthetic workbooks instead of masked real data

**Status:** Accepted

## Context

The source is six yearly Google Sheets workbooks with a household's real finances: amounts, dates, merchants, and who earned or paid what. The project is public, and its point is that anyone can clone it, run it and read the result. CI has to run the whole pipeline on every pull request, and the published dashboard needs data that looks like a household's.

What makes the source hard is its layout, not its values: credits and debits on the same sheet rows, owner and card encoded as cell colors (sometimes as `rgb`, sometimes as a `theme` index), installments typed as `(k/N)` rows that cross years, a column added in 2022, and a portfolio sheet that repeats its whole history in every file.

## Decision

The real workbooks never leave the owners' machine and never enter git. The repo ships a generator instead ([`synthetic/generate.py`](../../synthetic/generate.py)) that writes six workbooks with the same layout and the same quirks, from invented people (Person A, Person B), cards and merchants ([`synthetic/catalog.py`](../../synthetic/catalog.py)).

- The ingestion runs on the generated files unchanged; nothing in `ingestion/` or `dbt/` knows which source it reads.
- The output is deterministic for a given `--seed` and `--as-of`, so tests and CI always see the same data.
- `make data` generates and loads in one step, and CI runs exactly that. The published dashboard and dbt docs are built from it.
- [`.gitignore`](../../.gitignore) blocks the paths and formats real data would arrive in (`data/raw/*`, `*.xlsx`, `*.csv` outside the seeds, `*.duckdb`).

## Alternatives considered

- **Mask the real workbooks** (rename people and merchants, scale or shift the amounts and dates). Masking keeps the household's actual pattern of life: which months are tight, how often a given merchant appears, when a salary changes. Anyone who knows the household could recognize it, and a single masking mistake stays in the git history for good.
- **A handful of hand-written fixture rows.** Enough for unit tests, but not for the quirks that only appear at scale (the 2021 layout, installments that cross a year boundary, the cumulative portfolio sheet) and not enough for a dashboard worth reading.
- **A public dataset.** It would lose the problem the project exists to solve: meaning stored in cell colors across years of hand-kept workbooks.

## Consequences

- Anyone can clone and run the whole project with no credentials or real data, and CI needs no secrets.
- The generator doubles as documentation: its docstring and catalog list every quirk the pipeline must handle.
- Running end to end on the synthetic data caught two bugs before any real data was involved (the duplicate `transaction_id` and the portfolio totals loaded as holdings, in the README).
- The generator only reproduces the quirks known when it was written. The first run on the real workbooks found gaps it could not show (see [What the real workbooks taught](../../README.md#what-the-real-workbooks-taught)); each one has to be added to the generator by hand so CI covers it.
- The dashboard's numbers are fictional, and the generator is code to maintain alongside the pipeline.
