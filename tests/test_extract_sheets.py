"""End-to-end tests of the ingestion: synthetic workbooks → raw.* in DuckDB."""

from __future__ import annotations

import logging
import shutil
from collections import Counter
from pathlib import Path

import duckdb
import pytest

from ingestion.extract_sheets import run
from synthetic import catalog
from synthetic.generate import FILE_TEMPLATE, FIRST_YEAR, Generator


@pytest.fixture(scope="module")
def con(raw_db: Path):
    connection = duckdb.connect(str(raw_db), read_only=True)
    yield connection
    connection.close()


def _scalar(con, sql: str):
    return con.execute(sql).fetchone()[0]


def test_every_generated_row_is_loaded(con) -> None:
    generator = Generator().build()
    expected = Counter()
    for (year, _month), book in generator.ledger.items():
        expected[FILE_TEMPLATE.format(year=year)] += len(book.credits) + len(book.debits)

    loaded = dict(
        con.execute("select source_file, count(*) from raw.transacoes group by 1").fetchall()
    )
    assert loaded == dict(expected)


def test_2021_rows_have_no_macro_category(con) -> None:
    sql = f"""
        select count(*) from raw.transacoes
        where source_file = '{FILE_TEMPLATE.format(year=FIRST_YEAR)}'
          and macrocategoria_raw is not null
    """
    assert _scalar(con, sql) == 0


def test_categories_come_only_from_newest_workbook(con) -> None:
    expected = len(catalog.INCOME_CATEGORIES) + len(catalog.EXPENSE_CATEGORIES)
    assert _scalar(con, "select count(*) from raw.categorias_config") == expected


def test_reload_is_idempotent_and_logs_unknown_colors(
    synthetic_dir: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    xlsx_dir = tmp_path / "xlsx"
    xlsx_dir.mkdir()
    shutil.copy(synthetic_dir / FILE_TEMPLATE.format(year=FIRST_YEAR), xlsx_dir)
    db = tmp_path / "warehouse.duckdb"

    with caplog.at_level(logging.WARNING, logger="ingestion.extract_sheets"):
        run(xlsx_dir, db)
    with duckdb.connect(str(db), read_only=True) as connection:
        first_count = _scalar(connection, "select count(*) from raw.transacoes")

    run(xlsx_dir, db)
    with duckdb.connect(str(db), read_only=True) as connection:
        assert _scalar(connection, "select count(*) from raw.transacoes") == first_count

    assert "FFFF00" in caplog.text  # the stray highlight color


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Known bug: credits and debits share sheet rows, and transacao_id hashes only "
        "file|sheet|row, so both sides of a row get the same id."
    ),
)
def test_transaction_ids_are_unique(con) -> None:
    sql = "select count(*) - count(distinct transacao_id) from raw.transacoes"
    assert _scalar(con, sql) == 0


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Known bug: the 'Total:' label sits in column C, but iter_snapshot_rows only "
        "checks the first header column (B), so each block's total is loaded as a holding."
    ),
)
def test_snapshot_totals_are_not_loaded_as_holdings(con) -> None:
    sql = "select count(*) from raw.carteira_snapshots where aplicacao ilike 'total%'"
    assert _scalar(con, sql) == 0
