"""
Block detector for the "Situação Atual" (portfolio) sheet.

The sheet stacks blocks, each one a snapshot of the investment portfolio on
a given ``Data Referência`` (reference date). A typical block::

    Row N:    ... | Data Referência: | 2026-05-23 | ...
    Row N+1:  Banco/Corretora | Aplicação | Valor Bruto | Alocação | ...
    Row N+2+: <data rows>
    (blank rows until the next block)

Headers and column count change between snapshots (columns were added over
the years), so each block's header is resolved at runtime by matching known
header names.

Usage::

    wb = load_workbook("data/raw/2026.xlsx", data_only=True)
    ws = wb["Situação Atual"]
    for block in find_snapshot_blocks(ws):
        for row in iter_snapshot_rows(ws, block):
            print(block.reference_date, row)
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

# Marker that opens each block
REFERENCE_DATE_MARKER = "Data Referência"

# Columns the portfolio table can occupy. Columns M+ hold side notes
# (pending installments etc.) that are not part of the snapshot.
PORTFOLIO_MIN_COL = 1  # A
PORTFOLIO_MAX_COL = 12  # L


# Header as typed in the sheet (compared after _normalize) → canonical column
_HEADER_SYNONYMS: dict[str, str] = {
    "banco/corretora": "bank",
    "banco / corretora": "bank",
    "banco": "bank",
    "corretora": "bank",
    "aplicação": "asset",
    "aplicacao": "asset",
    "ativo": "asset",
    "valor bruto": "gross_value",
    "valor": "gross_value",
    "valor atual": "gross_value",
    "alocação": "allocation_pct",
    "alocacao": "allocation_pct",
    "% alocação": "allocation_pct",
    "% alocacao": "allocation_pct",
    "vencimento": "maturity_date",
    "mom": "mom",
    "m/m": "mom",
    "yoy": "yoy",
    "y/y": "yoy",
    "valor líquido final": "net_value_at_maturity",
    "valor liquido final": "net_value_at_maturity",
    "rendimento atual": "return_to_date",
    "rendimento final": "return_at_maturity",
}


# Text columns where a total row's label can appear.
_LABEL_COLUMNS = ("bank", "asset")
_TOTAL_LABEL = re.compile(r"total\s*:?")


@dataclass
class SnapshotBlock:
    """Where one snapshot block sits in the sheet."""

    reference_date: date
    """Date read from the ``Data Referência:`` marker."""

    marker_row: int
    """Row (1-based) of the marker."""

    header_row: int | None
    """Row (1-based) of the column header, or None for a text-only snapshot."""

    end_row: int
    """End of the block, exclusive: the first row that is NOT part of it."""

    header_map: dict[str, int] = field(default_factory=dict)
    """Canonical column name → column index (1-based)."""


def find_snapshot_blocks(ws: Any) -> list[SnapshotBlock]:
    """Find every snapshot block in a worksheet.

    Args:
        ws: openpyxl worksheet (usually ``wb["Situação Atual"]``).

    Returns:
        SnapshotBlocks in sheet order (oldest to newest). Blocks without a
        detectable header (e.g. the first snapshot, often a text summary)
        come back with ``header_row=None`` and ``header_map={}``, and the
        caller can skip them.
    """
    # Step 1: find every row with a "Data Referência" marker
    markers: list[tuple[int, int, date]] = []
    for row in ws.iter_rows():
        for cell in row:
            value = cell.value
            if value is not None and REFERENCE_DATE_MARKER in str(value):
                ref_date = _find_reference_date(ws, cell.row, cell.column)
                if ref_date is not None:
                    markers.append((cell.row, cell.column, ref_date))
                break  # one marker per row is enough

    if not markers:
        return []

    # Step 2: for each marker, find the header and the end of the block
    blocks: list[SnapshotBlock] = []
    for i, (marker_row, _marker_col, ref_date) in enumerate(markers):
        end_row = markers[i + 1][0] if i + 1 < len(markers) else ws.max_row + 1

        header_row, header_map = _find_header_row(ws, marker_row + 1, end_row)
        blocks.append(
            SnapshotBlock(
                reference_date=ref_date,
                marker_row=marker_row,
                header_row=header_row,
                end_row=end_row,
                header_map=header_map,
            )
        )

    return blocks


def iter_snapshot_rows(ws: Any, block: SnapshotBlock) -> Iterator[dict[str, Any]]:
    """Yield a block's data rows as dicts keyed by canonical column name.

    Skips empty rows and total rows ("Total:" in any label column, see
    ``_is_total_row``).

    Args:
        ws: worksheet.
        block: SnapshotBlock from ``find_snapshot_blocks``.

    Yields:
        dict {canonical_name: value} for each data row.
    """
    if block.header_row is None or not block.header_map:
        return

    for row in range(block.header_row + 1, block.end_row):
        record: dict[str, Any] = {}
        any_value = False
        for canonical, col in block.header_map.items():
            value = ws.cell(row, col).value
            record[canonical] = value
            if value is not None and str(value).strip() != "":
                any_value = True

        if not any_value:
            continue

        if _is_total_row(record):
            continue

        yield record


# --------------------------------------------------------------------------
# Internal helpers
# --------------------------------------------------------------------------


def _find_reference_date(ws: Any, row: int, marker_col: int) -> date | None:
    """Find the reference date next to the marker.

    The "Data Referência:" marker sits in one cell and the date usually in
    the cell to its right. Looks up to 5 columns ahead.
    """
    for col_offset in range(1, 6):
        cell = ws.cell(row, marker_col + col_offset)
        if cell.value is None:
            continue
        if isinstance(cell.value, datetime):
            return cell.value.date()
        if isinstance(cell.value, date):
            return cell.value
        # Best-effort parsing of a date typed as text
        text = str(cell.value).strip()
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
    return None


def _find_header_row(ws: Any, start: int, end: int) -> tuple[int | None, dict[str, int]]:
    """Find the first row in range with at least 2 known headers.

    Returns:
        (header_row, {canonical_name: col_index}) or (None, {}).
    """
    for row in range(start, end):
        header_map: dict[str, int] = {}
        for col in range(PORTFOLIO_MIN_COL, PORTFOLIO_MAX_COL + 1):
            cell_value = ws.cell(row, col).value
            canonical = _match_header(cell_value)
            if canonical and canonical not in header_map:
                header_map[canonical] = col
        if len(header_map) >= 2:
            return row, header_map
    return None, {}


def _is_total_row(record: dict[str, Any]) -> bool:
    """Total row: some label column holds only "Total" or "Total:".

    The label is not always in the block's first column: in the real
    workbook "Total:" sits in column C (Aplicação), with B (Banco/Corretora)
    empty.
    """
    for canonical in _LABEL_COLUMNS:
        value = record.get(canonical)
        if isinstance(value, str) and _TOTAL_LABEL.fullmatch(_normalize(value)):
            return True
    return False


def _match_header(value: Any) -> str | None:
    """Match a cell value against the known header synonyms."""
    if value is None:
        return None
    key = _normalize(str(value))
    if not key:
        return None
    return _HEADER_SYNONYMS.get(key)


def _normalize(text: str) -> str:
    """Lowercase and collapse whitespace, keeping accents."""
    return " ".join(text.strip().lower().split())
