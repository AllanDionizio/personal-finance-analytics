"""Tests for color_resolver.

Pure tests for `owner_from_hex` / `payment_method_from_hex`, plus integration
tests on the synthetic XLSX (or a real one, via env var).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ingestion.color_resolver import (
    OWNER_BY_HEX,
    OWNER_DEFAULT,
    PAYMENT_METHOD_BY_HEX,
    PAYMENT_METHOD_DEFAULT,
    load_theme_palette,
    owner_from_hex,
    payment_method_from_hex,
    resolve_cell_color,
    resolve_owner,
    resolve_payment_method,
)

# --------------------------------------------------------------------------
# Pure tests
# --------------------------------------------------------------------------


class TestOwnerFromHex:
    """Hex → owner mapping."""

    @pytest.mark.parametrize(
        "hex_color,expected",
        [
            ("4BACC6", "Person A"),
            ("F79646", "Person B"),
            ("FFFFFF", "Other"),
            ("000000", "Other"),
        ],
    )
    def test_known_colors(self, hex_color: str, expected: str) -> None:
        assert owner_from_hex(hex_color) == expected

    def test_case_insensitive(self) -> None:
        assert owner_from_hex("4bacc6") == "Person A"
        assert owner_from_hex("4BaCc6") == "Person A"

    def test_hash_prefix(self) -> None:
        assert owner_from_hex("#4BACC6") == "Person A"
        assert owner_from_hex("#f79646") == "Person B"

    def test_unknown_color_returns_default(self) -> None:
        assert owner_from_hex("ABCDEF") == OWNER_DEFAULT

    def test_none_returns_default(self) -> None:
        assert owner_from_hex(None) == OWNER_DEFAULT

    def test_canonical_mapping_values(self) -> None:
        assert set(OWNER_BY_HEX.values()) == {"Person A", "Person B", "Other"}


class TestPaymentMethodFromHex:
    """Hex → payment method mapping."""

    @pytest.mark.parametrize(
        "hex_color,expected",
        [
            ("B4A7D6", "Card A"),
            ("8E7CC3", "Card B"),
            ("b4a7d6", "Card A"),
            ("#8e7cc3", "Card B"),
            ("9FC5E8", "Card C"),
        ],
    )
    def test_known_colors(self, hex_color: str, expected: str) -> None:
        assert payment_method_from_hex(hex_color) == expected

    def test_unknown_color_returns_default(self) -> None:
        assert payment_method_from_hex("ABCDEF") == PAYMENT_METHOD_DEFAULT

    def test_none_returns_default(self) -> None:
        assert payment_method_from_hex(None) == PAYMENT_METHOD_DEFAULT

    def test_canonical_mapping_values(self) -> None:
        assert set(PAYMENT_METHOD_BY_HEX.values()) == {"Card A", "Card B", "Card C"}


# --------------------------------------------------------------------------
# Integration tests: synthetic or real XLSX
# --------------------------------------------------------------------------


class TestThemePalette:
    """Reads the theme palette from the XLSX."""

    def test_palette_has_12_entries(self, fixture_xlsx_path: Path) -> None:
        palette = load_theme_palette(fixture_xlsx_path)
        # The standard OOXML clrScheme has 12 colors
        assert len(palette) == 12

    def test_accent5_is_person_a(self, fixture_xlsx_path: Path) -> None:
        """Accent5 (index 8) is the teal used for Person A."""
        palette = load_theme_palette(fixture_xlsx_path)
        assert palette[8] == "4BACC6"

    def test_accent6_is_person_b(self, fixture_xlsx_path: Path) -> None:
        """Accent6 (index 9) is the orange used for Person B."""
        palette = load_theme_palette(fixture_xlsx_path)
        assert palette[9] == "F79646"

    def test_missing_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_theme_palette("/tmp/does_not_exist_zzz.xlsx")


@pytest.fixture(scope="module")
def wb(fixture_xlsx_path: Path):
    from openpyxl import load_workbook

    return load_workbook(fixture_xlsx_path, data_only=True)


@pytest.fixture(scope="module")
def palette(fixture_xlsx_path: Path) -> list[str | None]:
    return load_theme_palette(fixture_xlsx_path)


class TestResolveCellColorInWorkbook:
    """Resolves colors of XLSX cells read with openpyxl."""

    MONTH_SHEETS = (
        "JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"
    )  # fmt: skip

    def _first_cell(self, wb, col: int, source_type: str, hex_color: str, palette):
        """First cell in the column, on any month sheet, whose color comes
        from `source_type` and resolves to `hex_color`."""
        for sheet in self.MONTH_SHEETS:
            ws = wb[sheet]
            for row in range(16, ws.max_row + 1):
                cell = ws.cell(row, col)
                if cell.value is None:
                    continue
                result = resolve_cell_color(cell, palette)
                if result.source_type == source_type and result.hex == hex_color:
                    return cell
        pytest.fail(f"No {source_type} {hex_color} cell in column {col}")

    def test_rgb_color(self, wb, palette) -> None:
        """A Person A credit stored as rgb FF4BACC6 → 4BACC6."""
        cell = self._first_cell(wb, 4, "rgb", "4BACC6", palette)
        assert resolve_owner(cell, palette) == "Person A"

    def test_theme_color(self, wb, palette) -> None:
        """A Person B credit stored as theme=9 → F79646."""
        cell = self._first_cell(wb, 4, "theme", "F79646", palette)
        assert resolve_owner(cell, palette) == "Person B"

    def test_same_color_as_rgb_and_theme_resolves_the_same(self, wb, palette) -> None:
        """The Google Sheets quirk: Person A's color appears in both forms."""
        rgb = self._first_cell(wb, 4, "rgb", "4BACC6", palette)
        theme = self._first_cell(wb, 4, "theme", "4BACC6", palette)
        assert resolve_owner(rgb, palette) == resolve_owner(theme, palette) == "Person A"

    def test_card_a_debit(self, wb, palette) -> None:
        """Debits (column L) colored B4A7D6 map to Card A."""
        cell = self._first_cell(wb, 12, "rgb", "B4A7D6", palette)
        assert resolve_payment_method(cell, palette) == "Card A"
