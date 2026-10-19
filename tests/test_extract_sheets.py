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
from synthetic.generate import (
    FILE_TEMPLATE,
    FIRST_YEAR,
    LAST_YEAR,
    TEXT_SNAPSHOT_DATE,
    Generator,
)


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
        con.execute("select source_file, count(*) from raw.transactions group by 1").fetchall()
    )
    assert loaded == dict(expected)


def test_2021_rows_have_no_macro_category(con) -> None:
    sql = f"""
        select count(*) from raw.transactions
        where source_file = '{FILE_TEMPLATE.format(year=FIRST_YEAR)}'
          and macro_category is not null
    """
    assert _scalar(con, sql) == 0


def test_categories_come_only_from_newest_workbook(con) -> None:
    expected = len(catalog.INCOME_CATEGORIES) + len(catalog.EXPENSE_CATEGORIES)
    assert _scalar(con, "select count(*) from raw.category_config") == expected


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
        first_count = _scalar(connection, "select count(*) from raw.transactions")

    run(xlsx_dir, db)
    with duckdb.connect(str(db), read_only=True) as connection:
        assert _scalar(connection, "select count(*) from raw.transactions") == first_count

    assert "FFFF00" in caplog.text  # the stray highlight color


def test_transaction_ids_are_unique(con) -> None:
    """Credits and debits share sheet rows, so the id must include the side."""
    sql = "select count(*) - count(distinct transaction_id) from raw.transactions"
    assert _scalar(con, sql) == 0


def test_snapshot_totals_are_not_loaded_as_holdings(con) -> None:
    """Each block ends with a 'Total:' row labeled in column C, not B."""
    sql = "select count(*) from raw.portfolio_snapshots where asset ilike 'total%'"
    assert _scalar(con, sql) == 0


def test_snapshot_sums_match_the_portfolio(con) -> None:
    """Per snapshot, loaded holdings add up to the generated portfolio, whatever the
    total row's label: a leaked total row would double the sum."""
    expected = {
        s.when: round(sum(h.value for h in s.holdings), 2)
        for s in Generator().build().snapshots
        if s.when != TEXT_SNAPSHOT_DATE
    }
    sql = f"""
        select reference_date, sum(gross_value) from raw.portfolio_snapshots
        where source_file = '{FILE_TEMPLATE.format(year=LAST_YEAR)}'
        group by 1
    """
    loaded = {when: round(float(total), 2) for when, total in con.execute(sql).fetchall()}
    assert loaded == expected


def test_every_workbook_has_its_theme_palette(con) -> None:
    files = {
        f for (f,) in con.execute("select distinct source_file from raw.transactions").fetchall()
    }
    themed = {
        f for (f,) in con.execute("select distinct source_file from raw.workbook_themes").fetchall()
    }
    assert themed == files


def test_theme_colors_resolve_through_the_workbook_palette(con) -> None:
    """Every theme reference in a transaction has a palette entry in the same file,
    and the owner indexes resolve to the owners' hex colors."""
    sql = """
        select t.amount_color_value::int as theme_index, th.hex, count(*)
        from raw.transactions t
        left join raw.workbook_themes th
          on th.source_file = t.source_file
         and th.theme_index = t.amount_color_value::int
        where t.amount_color_type = 'theme'
        group by all
    """
    resolved = {idx: hex_color for idx, hex_color, _ in con.execute(sql).fetchall()}
    assert resolved == {
        catalog.PERSON_A_THEME: catalog.PERSON_A_RGB[2:],
        catalog.PERSON_B_THEME: catalog.PERSON_B_RGB[2:],
    }
