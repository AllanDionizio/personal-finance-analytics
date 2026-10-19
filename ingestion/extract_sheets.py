"""
Literal extraction of the source workbooks into DuckDB's ``raw.*`` layer.

Reads every ``.xlsx`` in ``--xlsx-dir`` and loads four tables:

- ``raw.transactions``        — one row per transaction (credit side and
  debit side of the month sheets), with cell colors kept as raw data.
- ``raw.portfolio_snapshots`` — historical snapshots from the "Situação
  Atual" sheet.
- ``raw.category_config``     — the canonical category list (2026 file only).
- ``raw.workbook_themes``     — each workbook's theme palette, so staging can
  resolve ``theme`` color references per file.

Raw layer principles (see ``docs/data-model.md``):

- **No transformation**: literal capture, with provenance (``source_file``,
  ``source_sheet``, ``source_row``). Cleaning, typing, installment parsing and
  color → owner/payment method mapping belong to dbt staging. That is why
  this module does **not** use ``installment_parser`` (descriptions keep their
  ``(N/M)`` tag) and uses ``color_resolver`` only to *detect and log*
  unrecognized colors.
- **Literal values**: column names are English; cell values stay as typed in
  the Portuguese source (``'Sim'``, ``'Mercado'``, ``'Fixo'``).
- **Idempotency**: re-running on the same XLSX gives the same result. Each
  file is reloaded with DELETE-by-``source_file`` + INSERT, and
  ``transaction_id`` is deterministic (see ``_transaction_id``).
- **Dynamic schema**: debit columns differ between 2021 (no MacroCategoria)
  and 2022+; the header is detected at runtime, not by fixed position.

CLI::

    python -m ingestion.extract_sheets --xlsx-dir data/raw --db data/warehouse.duckdb
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import duckdb
from openpyxl import load_workbook

from ingestion.color_resolver import (
    OWNER_BY_HEX,
    PAYMENT_METHOD_BY_HEX,
    load_theme_palette,
    resolve_cell_color,
)
from ingestion.snapshot_blocks import find_snapshot_blocks, iter_snapshot_rows

log = logging.getLogger("ingestion.extract_sheets")

DEFAULT_XLSX_DIR = Path("data/raw")
DEFAULT_DB = Path("data/warehouse.duckdb")

# File whose "Configurações" sheet is the canonical category list.
CONFIG_SOURCE_YEAR = 2026

# "Configurações" sheet: columns and row range (1-based).
_CONFIG_ROW_START = 4
_CONFIG_ROW_END = 38  # inclusive
_CONFIG_COL_INCOME = 9  # I
_CONFIG_COL_EXPENSE = 10  # J
_CONFIG_COL_MACRO = 11  # K
_CONFIG_PLACEHOLDER = "-"  # empty/placeholder cell to skip


# --------------------------------------------------------------------------
# Sheet identification (sheet names are Portuguese in the source)
# --------------------------------------------------------------------------

_MONTH_PREFIXES = {
    "jan",
    "fev",
    "mar",
    "abr",
    "mai",
    "jun",
    "jul",
    "ago",
    "set",
    "out",
    "nov",
    "dez",
}


def _is_month_sheet(name: str) -> bool:
    """True if the sheet name looks like a month (``JAN``, ``Fevereiro``, ``MAR/26``, ...)."""
    key = name.strip().lower()
    return len(key) >= 3 and key[:3] in _MONTH_PREFIXES


def _is_portfolio_sheet(name: str) -> bool:
    key = " ".join(name.strip().lower().split())
    return "situacao atual" in key or "situação atual" in key


def _is_config_sheet(name: str) -> bool:
    return name.strip().lower().startswith("configura")


def _parse_year(filename: str) -> int | None:
    """Extract the year (20XX) from the file name, e.g. ``2026.xlsx`` → 2026."""
    m = re.search(r"(20\d{2})", filename)
    return int(m.group(1)) if m else None


# --------------------------------------------------------------------------
# Month sheet layout detection (2021 vs 2022+)
# --------------------------------------------------------------------------

# Header as typed (normalized) → canonical field name.
_MONTH_HEADER_SYNONYMS: dict[str, str] = {
    "descrição": "description",
    "descricao": "description",
    "categoria": "category",
    "categorias": "category",
    "macrocategoria": "macro_category",
    "macro categoria": "macro_category",
    "macro-categoria": "macro_category",
    "macro": "macro_category",
    "valor": "amount",
    "valores": "amount",
    "data": "date",
    "ok": "status",
    "ok?": "status",
    "status": "status",
    "pago": "status",
}

# Heuristic split between the credit side (B-G) and the debit side (I-O)
# when only one "Descrição" header is found.
_CREDIT_MAX_COL = 7  # G


@dataclass
class MonthLayout:
    """Column map detected for a month sheet."""

    header_row: int
    credit: dict[str, int] = field(default_factory=dict)
    debit: dict[str, int] = field(default_factory=dict)


def _match_month_header(value: Any) -> str | None:
    if value is None:
        return None
    key = " ".join(str(value).strip().lower().split())
    return _MONTH_HEADER_SYNONYMS.get(key)


def detect_month_layout(ws: Any) -> MonthLayout | None:
    """Detect the header row and the credit/debit column maps.

    Scans the first rows for the one with the most known headers (requiring
    at least ``description`` + ``amount``). Credit and debit sides are split
    at the second "Descrição": everything to its left is credit, the rest is
    debit. This picks up the column shift between 2021 (no MacroCategoria)
    and 2022+ without fixed positions.

    Returns:
        MonthLayout, or None if no plausible header row is found.
    """
    max_row = min(ws.max_row, 25)
    max_col = min(ws.max_column, 20)
    best: tuple[int, list[tuple[int, str]]] | None = None

    for r in range(1, max_row + 1):
        matches: list[tuple[int, str]] = []
        for c in range(1, max_col + 1):
            canonical = _match_month_header(ws.cell(r, c).value)
            if canonical:
                matches.append((c, canonical))
        canons = {k for _, k in matches}
        has_min = "description" in canons and "amount" in canons
        if has_min and (best is None or len(matches) > len(best[1])):
            best = (r, matches)

    if best is None:
        return None

    header_row, matches = best
    desc_cols = sorted(c for c, k in matches if k == "description")

    layout = MonthLayout(header_row=header_row)
    if len(desc_cols) >= 2:
        split = desc_cols[-1]  # first column of the debit side
        for c, k in matches:
            side = layout.credit if c < split else layout.debit
            side.setdefault(k, c)
    else:
        # Only one side has a detectable header: pick it by column position.
        target = layout.credit if desc_cols[0] <= _CREDIT_MAX_COL else layout.debit
        for c, k in matches:
            target.setdefault(k, c)

    return layout


# --------------------------------------------------------------------------
# Raw value coercion
# --------------------------------------------------------------------------

_NULLISH = {"", "-", "n/a", "na"}


def _to_str(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
    s = str(value).strip()
    if s.lower() in _NULLISH:
        return None
    s = s.replace("R$", "").replace("%", "").replace(" ", "").replace("\xa0", "")
    # pt-BR "1.234,56" → "1234.56"
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _to_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if s.lower() in _NULLISH:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


# --------------------------------------------------------------------------
# Raw colors + tracking of unrecognized colors
# --------------------------------------------------------------------------


def _raw_cell_color(cell: Any) -> tuple[str | None, str | None]:
    """Extract the raw (type, value) of the background color, theme unresolved.

    - rgb   → ("rgb", "FF4BACC6")   (literal ARGB hex)
    - theme → ("theme", "8")        (theme index, as a string)
    - no fill / other → (None, None) or the literal (type, value).
    """
    if cell is None:
        return (None, None)
    fill = getattr(cell, "fill", None)
    color = getattr(fill, "start_color", None) if fill is not None else None
    if color is None:
        return (None, None)
    ctype = getattr(color, "type", None)
    if ctype == "rgb":
        val = color.value
        return ("rgb", str(val)) if val is not None else (None, None)
    if ctype == "theme":
        return ("theme", str(color.value))
    if ctype is None:
        return (None, None)
    val = getattr(color, "value", None)
    return (ctype, str(val) if val is not None else None)


def _track_color(cell: Any, palette: list[str | None], unrecognized: Counter) -> None:
    """Resolve the cell's color and count it if it's not recognized.

    "Recognized" means it maps to a known owner or payment method (including
    white/black/no fill, which become 'Other'). Any other color is counted
    for one aggregated warning; it never fails the run.
    """
    if cell is None:
        return
    hex_color = resolve_cell_color(cell, palette).hex
    if hex_color is None:
        return
    if hex_color in OWNER_BY_HEX or hex_color in PAYMENT_METHOD_BY_HEX:
        return
    unrecognized[hex_color] += 1


# --------------------------------------------------------------------------
# Idempotency
# --------------------------------------------------------------------------


def _transaction_id(source_file: str, source_sheet: str, source_row: int, side: str) -> str:
    """sha256(source_file|source_sheet|source_row|side)[:16].

    Deterministic: re-running on the same XLSX gives the same id. If the row
    moves, the id changes (the source of truth is the XLSX, not the entity).
    ``side`` is part of the hash because credit and debit share each sheet row.
    """
    raw = f"{source_file}|{source_sheet}|{source_row}|{side}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------


def _read_transaction(
    ws: Any,
    row: int,
    side: str,
    colmap: dict[str, int],
    source_file: str,
    palette: list[str | None],
    unrecognized: Counter,
    extracted_at: datetime,
) -> tuple | None:
    """Read one side (credit or debit) of a row; None if that side is empty."""
    desc_col = colmap.get("description")
    amount_col = colmap.get("amount")
    date_col = colmap.get("date")

    description = _to_str(ws.cell(row, desc_col).value) if desc_col else None
    amount = _to_decimal(ws.cell(row, amount_col).value) if amount_col else None
    when = _to_date(ws.cell(row, date_col).value) if date_col else None

    # Empty side: description, amount AND date all null. A zero amount is kept.
    if description is None and amount is None and when is None:
        return None

    cat_col = colmap.get("category")
    macro_col = colmap.get("macro_category")
    status_col = colmap.get("status")

    category = _to_str(ws.cell(row, cat_col).value) if cat_col else None
    macro_category = _to_str(ws.cell(row, macro_col).value) if macro_col else None
    status = _to_str(ws.cell(row, status_col).value) if status_col else None

    desc_cell = ws.cell(row, desc_col) if desc_col else None
    amount_cell = ws.cell(row, amount_col) if amount_col else None
    desc_color_type, desc_color_value = _raw_cell_color(desc_cell)
    amount_color_type, amount_color_value = _raw_cell_color(amount_cell)
    _track_color(desc_cell, palette, unrecognized)
    _track_color(amount_cell, palette, unrecognized)

    return (
        _transaction_id(source_file, ws.title, row, side),
        source_file,
        ws.title,
        row,
        extracted_at,
        side,
        description,
        category,
        macro_category,
        amount,
        when,
        status,
        desc_color_type,
        desc_color_value,
        amount_color_type,
        amount_color_value,
    )


def extract_transactions(
    ws: Any,
    source_file: str,
    palette: list[str | None],
    unrecognized: Counter,
    extracted_at: datetime,
) -> list[tuple]:
    """Extract the transactions (credit + debit) of one month sheet."""
    layout = detect_month_layout(ws)
    if layout is None:
        log.warning("  sheet %r: transaction header not found, skipping", ws.title)
        return []

    rows: list[tuple] = []
    for row in range(layout.header_row + 1, ws.max_row + 1):
        for side, colmap in (("credit", layout.credit), ("debit", layout.debit)):
            if not colmap or "description" not in colmap:
                continue
            rec = _read_transaction(
                ws, row, side, colmap, source_file, palette, unrecognized, extracted_at
            )
            if rec is not None:
                rows.append(rec)
    return rows


def extract_snapshots(ws: Any, source_file: str, extracted_at: datetime) -> list[tuple]:
    """Extract every portfolio snapshot from the "Situação Atual" sheet."""
    rows: list[tuple] = []
    for block in find_snapshot_blocks(ws):
        for rec in iter_snapshot_rows(ws, block):
            rows.append(
                (
                    source_file,
                    block.marker_row,
                    extracted_at,
                    block.reference_date,
                    _to_str(rec.get("bank")),
                    _to_str(rec.get("asset")),
                    _to_decimal(rec.get("gross_value")),
                    _to_decimal(rec.get("allocation_pct")),
                    _to_date(rec.get("maturity_date")),
                    _to_decimal(rec.get("mom")),
                    _to_decimal(rec.get("yoy")),
                    _to_decimal(rec.get("net_value_at_maturity")),
                    _to_decimal(rec.get("return_to_date")),
                    _to_decimal(rec.get("return_at_maturity")),
                )
            )
    return rows


def extract_categories(ws: Any) -> list[tuple]:
    """Extract the category list from the "Configurações" sheet."""
    rows: list[tuple] = []
    for r in range(_CONFIG_ROW_START, _CONFIG_ROW_END + 1):
        income = _to_str(ws.cell(r, _CONFIG_COL_INCOME).value)
        expense = _to_str(ws.cell(r, _CONFIG_COL_EXPENSE).value)
        macro = _to_str(ws.cell(r, _CONFIG_COL_MACRO).value)

        if income and income != _CONFIG_PLACEHOLDER:
            rows.append(("income", income, None))
        if expense and expense != _CONFIG_PLACEHOLDER:
            macro_val = macro if (macro and macro != _CONFIG_PLACEHOLDER) else None
            rows.append(("expense", expense, macro_val))
    return rows


# --------------------------------------------------------------------------
# DuckDB: schema + idempotent load
# --------------------------------------------------------------------------

_DDL = """
CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE IF NOT EXISTS raw.transactions (
    transaction_id          VARCHAR,
    source_file             VARCHAR,
    source_sheet            VARCHAR,
    source_row              INTEGER,
    extracted_at            TIMESTAMP,
    side                    VARCHAR,
    description             VARCHAR,
    category                VARCHAR,
    macro_category          VARCHAR,
    amount                  DECIMAL(12, 2),
    transaction_date        DATE,
    status                  VARCHAR,
    description_color_type  VARCHAR,
    description_color_value VARCHAR,
    amount_color_type       VARCHAR,
    amount_color_value      VARCHAR
);

CREATE TABLE IF NOT EXISTS raw.portfolio_snapshots (
    source_file           VARCHAR,
    source_block_row      INTEGER,
    extracted_at          TIMESTAMP,
    reference_date        DATE,
    bank                  VARCHAR,
    asset                 VARCHAR,
    gross_value           DECIMAL(12, 2),
    allocation_pct        DECIMAL(8, 6),
    maturity_date         DATE,
    mom                   DECIMAL(10, 6),
    yoy                   DECIMAL(10, 6),
    net_value_at_maturity DECIMAL(12, 2),
    return_to_date        DECIMAL(18, 6),
    return_at_maturity    DECIMAL(18, 6)
);

CREATE TABLE IF NOT EXISTS raw.category_config (
    category_type  VARCHAR,
    category       VARCHAR,
    macro_category VARCHAR
);

CREATE TABLE IF NOT EXISTS raw.workbook_themes (
    source_file  VARCHAR,
    extracted_at TIMESTAMP,
    theme_index  INTEGER,
    hex          VARCHAR
);
"""

_INSERT_TRANSACTIONS = "INSERT INTO raw.transactions VALUES (" + ",".join(["?"] * 16) + ")"
_INSERT_SNAPSHOTS = "INSERT INTO raw.portfolio_snapshots VALUES (" + ",".join(["?"] * 14) + ")"
_INSERT_CATEGORIES = "INSERT INTO raw.category_config VALUES (?, ?, ?)"
_INSERT_THEMES = "INSERT INTO raw.workbook_themes VALUES (?, ?, ?, ?)"


def _create_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(_DDL)


def _reload_transactions(
    con: duckdb.DuckDBPyConnection, source_file: str, rows: list[tuple]
) -> None:
    con.execute("DELETE FROM raw.transactions WHERE source_file = ?", [source_file])
    if rows:
        con.executemany(_INSERT_TRANSACTIONS, rows)


def _reload_snapshots(con: duckdb.DuckDBPyConnection, source_file: str, rows: list[tuple]) -> None:
    con.execute("DELETE FROM raw.portfolio_snapshots WHERE source_file = ?", [source_file])
    if rows:
        con.executemany(_INSERT_SNAPSHOTS, rows)


def _reload_categories(con: duckdb.DuckDBPyConnection, rows: list[tuple]) -> None:
    con.execute("DELETE FROM raw.category_config")
    if rows:
        con.executemany(_INSERT_CATEGORIES, rows)


def _reload_themes(con: duckdb.DuckDBPyConnection, source_file: str, rows: list[tuple]) -> None:
    con.execute("DELETE FROM raw.workbook_themes WHERE source_file = ?", [source_file])
    if rows:
        con.executemany(_INSERT_THEMES, rows)


def theme_rows(source_file: str, palette: list[str | None], extracted_at: datetime) -> list[tuple]:
    """One row per theme index, in the order ``theme`` color references use.

    Entries that can't be resolved statically keep a NULL hex, so the index
    positions stay aligned with the workbook.
    """
    return [(source_file, extracted_at, i, hex_color) for i, hex_color in enumerate(palette)]


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


def process_file(
    con: duckdb.DuckDBPyConnection,
    path: Path,
    extracted_at: datetime,
    unrecognized: Counter,
) -> None:
    """Process one XLSX, reloading its raw tables."""
    source_file = path.name
    log.info("Processing %s", source_file)

    palette = load_theme_palette(path)
    wb = load_workbook(path, data_only=True)
    year = _parse_year(source_file)

    transactions: list[tuple] = []
    snapshots: list[tuple] = []
    categories: list[tuple] = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        if _is_month_sheet(sheet_name):
            transactions.extend(
                extract_transactions(ws, source_file, palette, unrecognized, extracted_at)
            )
        elif _is_portfolio_sheet(sheet_name):
            snapshots.extend(extract_snapshots(ws, source_file, extracted_at))
        elif _is_config_sheet(sheet_name) and year == CONFIG_SOURCE_YEAR:
            categories.extend(extract_categories(ws))

    _reload_themes(con, source_file, theme_rows(source_file, palette, extracted_at))
    _reload_transactions(con, source_file, transactions)
    _reload_snapshots(con, source_file, snapshots)
    if categories:
        _reload_categories(con, categories)

    log.info(
        "  %d transactions, %d snapshot rows, %d categories",
        len(transactions),
        len(snapshots),
        len(categories),
    )


def run(xlsx_dir: str | Path, db_path: str | Path) -> None:
    """Run the full extraction over every XLSX in ``xlsx_dir``."""
    xlsx_dir = Path(xlsx_dir)
    db_path = Path(db_path)

    files = sorted(p for p in xlsx_dir.glob("*.xlsx") if not p.name.startswith("~$"))
    if not files:
        log.warning("No XLSX found in %s", xlsx_dir)
        return

    db_path.parent.mkdir(parents=True, exist_ok=True)
    extracted_at = datetime.now()
    unrecognized: Counter = Counter()

    con = duckdb.connect(str(db_path))
    try:
        _create_schema(con)
        for path in files:
            process_file(con, path, extracted_at, unrecognized)
    finally:
        con.close()

    if unrecognized:
        log.warning(
            "Unrecognized colors (hex → count): %s",
            dict(unrecognized.most_common()),
        )
    else:
        log.info("All colors recognized.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m ingestion.extract_sheets",
        description="Extract the source workbooks into DuckDB's raw.* layer.",
    )
    parser.add_argument(
        "--xlsx-dir",
        type=Path,
        default=DEFAULT_XLSX_DIR,
        help="Directory with the .xlsx files (default: data/raw).",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help="DuckDB file path (default: data/warehouse.duckdb).",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    run(args.xlsx_dir, args.db)


if __name__ == "__main__":
    main()
