# 2. Keep the raw layer literal and parse in dbt

**Status:** Accepted

## Context

The workbooks are typed by hand. The rules that turn them into facts (where an installment tag sits in a description, which color means which owner or card, how a legacy category maps to the current list) were bound to change as more of the data was read; the first run on the real workbooks already turned up rules that need to change (see [What the real workbooks taught](../../README.md#what-the-real-workbooks-taught)). Each workbook is also a file someone keeps editing, so the same file is loaded again many times.

## Decision

The ingestion ([`ingestion/extract_sheets.py`](../../ingestion/extract_sheets.py)) copies cells into `raw.*` as they are and does nothing else:

- descriptions keep their `(N/M)` installment tag; colors are stored as their type and value (`rgb` hex or `theme` index), and each workbook's theme palette goes to `raw.workbook_themes`;
- cell values stay in Portuguese as typed (`'Sim'`, `'Mercado'`, `'Fixo'`); only the column names are English;
- every row carries its provenance (`source_file`, `source_sheet`, `source_row`), and a file is reloaded with a delete by `source_file` and an insert, so a rerun gives the same result;
- `color_resolver` is used only to detect and log colors nobody recognizes, not to map them.

Cleaning, typing, installment parsing and the color mapping all happen in dbt staging ([`stg_transactions`](../../dbt/models/staging/stg_transactions.sql) and the [`clean_description`](../../dbt/macros/clean_description.sql) macro).

## Alternatives considered

- **Parse during ingestion, in Python.** openpyxl already has the cells in hand, and `ingestion/installment_parser.py` already implements the installment rule. But every rule change would mean reading every workbook again, and the rules would live outside dbt's lineage, tests and docs.
- **A generic loader (an ELT tool or a CSV export).** These read cell values, not cell fills, so the owner and card would be lost before the warehouse.

## Consequences

- A rule change is a dbt change, replayed with `dbt build` without touching the workbooks, and it is covered by dbt unit tests on hand-made rows.
- Any fact row can be traced back to the file, sheet and row it came from, and [`assert_transactions_reconcile_to_raw`](../../dbt/tests/assert_transactions_reconcile_to_raw.sql) checks that every raw transaction reaches the fact with its amount.
- The raw tables are not fit for analysis on their own: descriptions still carry tags and owners are still colors.
- The installment rule exists twice: in `ingestion/installment_parser.py`, which the pipeline does not call and only its tests use, and in dbt staging (the tag extraction in `stg_transactions` and the `clean_description` macro). They already differ on one input: an untagged `A - - B` stays as typed in Python and becomes `A - B` in dbt.
