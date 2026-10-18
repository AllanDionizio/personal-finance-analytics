"""Tests for snapshot_blocks. Run on the synthetic XLSX (or a real one, via env var)."""

from __future__ import annotations

import itertools
from datetime import date
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

from ingestion.snapshot_blocks import (
    SnapshotBlock,
    find_snapshot_blocks,
    iter_snapshot_rows,
)


@pytest.fixture(scope="module")
def portfolio_sheet(fixture_xlsx_path: Path):
    """The 'Situação Atual' worksheet of the fixture XLSX."""
    wb = load_workbook(fixture_xlsx_path, data_only=True)
    return wb["Situação Atual"]


class TestFindSnapshotBlocks:
    def test_finds_blocks(self, portfolio_sheet) -> None:
        blocks = find_snapshot_blocks(portfolio_sheet)
        assert len(blocks) > 0

    def test_blocks_in_chronological_order(self, portfolio_sheet) -> None:
        blocks = find_snapshot_blocks(portfolio_sheet)
        dates = [b.reference_date for b in blocks]
        assert dates == sorted(dates), "Blocks are not in chronological order"

    def test_every_block_has_a_date(self, portfolio_sheet) -> None:
        blocks = find_snapshot_blocks(portfolio_sheet)
        for block in blocks:
            assert isinstance(block.reference_date, date)

    def test_end_row_after_marker(self, portfolio_sheet) -> None:
        blocks = find_snapshot_blocks(portfolio_sheet)
        for block in blocks:
            assert block.end_row > block.marker_row

    def test_blocks_do_not_overlap(self, portfolio_sheet) -> None:
        """A block's end_row <= the next block's marker_row."""
        blocks = find_snapshot_blocks(portfolio_sheet)
        for prev, curr in itertools.pairwise(blocks):
            assert prev.end_row <= curr.marker_row


class TestHeaderDetection:
    def test_table_blocks_have_a_header(self, portfolio_sheet) -> None:
        """Snapshots from 2022-09 on are tables with a detectable header."""
        blocks = find_snapshot_blocks(portfolio_sheet)
        with_header = [b for b in blocks if b.header_row is not None]
        assert len(with_header) > 0

    def test_header_has_bank_asset_and_value(self, portfolio_sheet) -> None:
        blocks = find_snapshot_blocks(portfolio_sheet)
        for block in blocks:
            if block.header_row is None:
                continue
            assert "bank" in block.header_map
            assert "asset" in block.header_map
            assert "gross_value" in block.header_map

    def test_header_grows_over_time(self, portfolio_sheet) -> None:
        """Recent snapshots have more columns than old ones."""
        blocks = [b for b in find_snapshot_blocks(portfolio_sheet) if b.header_row is not None]
        if len(blocks) < 5:
            pytest.skip("Not enough snapshots to test header growth")
        first = blocks[:3]
        last = blocks[-3:]
        old_mean = sum(len(b.header_map) for b in first) / len(first)
        recent_mean = sum(len(b.header_map) for b in last) / len(last)
        assert recent_mean > old_mean


class TestIterSnapshotRows:
    def test_yields_data_rows(self, portfolio_sheet) -> None:
        """The newest block yields at least one data row."""
        blocks = [b for b in find_snapshot_blocks(portfolio_sheet) if b.header_row is not None]
        assert blocks, "No block with a header: unsuitable fixture"

        rows = list(iter_snapshot_rows(portfolio_sheet, blocks[-1]))
        assert len(rows) > 0

    def test_rows_have_canonical_keys(self, portfolio_sheet) -> None:
        blocks = [b for b in find_snapshot_blocks(portfolio_sheet) if b.header_row is not None]
        rows = list(iter_snapshot_rows(portfolio_sheet, blocks[-1]))
        for row in rows:
            assert "bank" in row or "asset" in row

    def test_skips_empty_rows(self, portfolio_sheet) -> None:
        """No yielded row has ALL columns empty."""
        blocks = [b for b in find_snapshot_blocks(portfolio_sheet) if b.header_row is not None]
        for block in blocks[:5]:  # first 5, for speed
            for row in iter_snapshot_rows(portfolio_sheet, block):
                has_value = any(v is not None and str(v).strip() != "" for v in row.values())
                assert has_value

    def test_block_without_header_yields_nothing(self, portfolio_sheet) -> None:
        fake_block = SnapshotBlock(
            reference_date=date(2020, 1, 1),
            marker_row=1,
            header_row=None,
            end_row=10,
            header_map={},
        )
        rows = list(iter_snapshot_rows(portfolio_sheet, fake_block))
        assert rows == []


class TestRegression:
    """Specific cases observed in the 2026 workbook."""

    def test_snapshot_2022_08_25_exists(self, portfolio_sheet) -> None:
        """The first known snapshot is 2022-08-25."""
        blocks = find_snapshot_blocks(portfolio_sheet)
        dates = [b.reference_date for b in blocks]
        assert date(2022, 8, 25) in dates

    def test_first_snapshot_is_text_without_header(self, portfolio_sheet) -> None:
        """The first snapshot was written as free text, not as a table."""
        first = find_snapshot_blocks(portfolio_sheet)[0]
        assert first.header_row is None
        assert list(iter_snapshot_rows(portfolio_sheet, first)) == []


class TestTotalRow:
    """Total rows must not load as holdings."""

    @pytest.fixture
    def ws(self):
        ws = Workbook().active
        ws["B2"], ws["C2"] = "Data Referência:", date(2025, 3, 25)
        ws["B3"], ws["C3"], ws["D3"] = "Banco/Corretora", "Aplicação", "Valor Bruto"
        ws["B4"], ws["C4"], ws["D4"] = "Banco X", "Total Return Fund", 100.0
        ws["B5"], ws["C5"], ws["D5"] = "Banco Y", "CDB", 200.0
        return ws

    def _assets(self, ws) -> list[str]:
        (block,) = find_snapshot_blocks(ws)
        return [r["asset"] for r in iter_snapshot_rows(ws, block)]

    @pytest.mark.parametrize("label_cell", ["B7", "C7"])
    def test_total_in_any_label_column(self, ws, label_cell: str) -> None:
        ws[label_cell], ws["D7"] = "Total:", 300.0
        assert self._assets(ws) == ["Total Return Fund", "CDB"]

    def test_case_and_whitespace_variations(self, ws) -> None:
        ws["C7"], ws["D7"] = "  TOTAL  ", 300.0
        assert self._assets(ws) == ["Total Return Fund", "CDB"]
