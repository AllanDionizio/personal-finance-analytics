"""Tests for the household context report's formatting."""

from __future__ import annotations

from datetime import date

import pytest

from reports.household_context import brl, day_label, month_label, pct, table


@pytest.mark.parametrize(
    ("value", "expected"),
    [(1234567.4, "R$ 1.234.567"), (0, "R$ 0"), (-9900, "R$ -9.900"), (None, "-")],
)
def test_brl_uses_brazilian_separators(value, expected):
    assert brl(value) == expected


def test_pct_uses_a_decimal_comma():
    assert pct(0.1255) == "12,6%"
    assert pct(0.04, 0) == "4%"
    assert pct(None) == "-"


def test_month_and_day_labels():
    assert month_label(date(2026, 9, 1)) == "set/2026"
    assert month_label(None) == "-"
    assert day_label(date(2026, 10, 19)) == "19/10/2026"
    assert day_label(None) == ""


def test_table_is_markdown():
    assert table(["A", "B"], [["1", "2"]]) == "| A | B |\n|---|---|\n| 1 | 2 |"
