"""Tests for installment_parser. Pure tests, no external fixtures."""

from __future__ import annotations

import pytest

from ingestion.installment_parser import InstallmentInfo, parse_installment


class TestParseInstallmentBasics:
    """Basic cases: no tag, tag at the end, empty input."""

    def test_no_installment(self) -> None:
        result = parse_installment("Mercado")
        assert result == InstallmentInfo("Mercado", 1, 1, False)

    def test_installment_at_the_end(self) -> None:
        result = parse_installment("Telha Norte (7/10)")
        assert result == InstallmentInfo("Telha Norte", 7, 10, True)

    def test_empty_description(self) -> None:
        result = parse_installment("")
        assert result == InstallmentInfo("", 1, 1, False)

    def test_none_description(self) -> None:
        result = parse_installment(None)
        assert result == InstallmentInfo("", 1, 1, False)

    def test_whitespace_only(self) -> None:
        result = parse_installment("   ")
        assert result == InstallmentInfo("", 1, 1, False)

    def test_whitespace_is_collapsed_without_a_tag(self) -> None:
        result = parse_installment("Pet shop -  Ração")
        assert result == InstallmentInfo("Pet shop - Ração", 1, 1, False)


class TestParseInstallmentPositions:
    """The (N/M) tag in different positions of the description."""

    def test_installment_in_the_middle(self) -> None:
        result = parse_installment("Amazon (4/4) - Smart Lock")
        assert result.clean_description == "Amazon - Smart Lock"
        assert result.installment_number == 4
        assert result.installment_count == 4
        assert result.is_installment is True

    def test_installment_at_the_start(self) -> None:
        result = parse_installment("(1/12) Compra Mac")
        assert result.clean_description == "Compra Mac"
        assert result.installment_number == 1
        assert result.installment_count == 12

    def test_extra_whitespace(self) -> None:
        result = parse_installment("Item   (2/3)   ")
        assert result.clean_description == "Item"
        assert result.installment_number == 2
        assert result.installment_count == 3

    def test_whitespace_inside_the_tag(self) -> None:
        # Tolerated: "(2 / 3)" and "(2/ 3)"
        result = parse_installment("Item (2 / 3)")
        assert result.installment_number == 2
        assert result.installment_count == 3


class TestParseInstallmentEdgeCases:
    """Edge cases and variations."""

    def test_single_installment_is_not_an_installment(self) -> None:
        """(1/1) means paid at once."""
        result = parse_installment("Item (1/1)")
        assert result.installment_number == 1
        assert result.installment_count == 1
        assert result.is_installment is False

    def test_tag_only(self) -> None:
        """A string that is only `(N/M)` gives an empty description."""
        result = parse_installment("(3/5)")
        assert result.clean_description == ""
        assert result.installment_number == 3
        assert result.installment_count == 5

    def test_accents_preserved(self) -> None:
        result = parse_installment("Mecânica do João (2/6)")
        assert result.clean_description == "Mecânica do João"

    def test_fraction_without_parentheses_is_not_an_installment(self) -> None:
        """`10/12` without parentheses is not an installment."""
        result = parse_installment("Café Sabor 10/12 Premium")
        assert result.clean_description == "Café Sabor 10/12 Premium"
        assert result.is_installment is False

    @pytest.mark.parametrize(
        "description,expected_desc,n,m",
        [
            ("Aquacenter (10/12)", "Aquacenter", 10, 12),
            ("Casa  (6/24)  Item", "Casa Item", 6, 24),
            ("X-Y-Z (1/3)", "X-Y-Z", 1, 3),
            ("Detalhe (12/48) — anotação", "Detalhe — anotação", 12, 48),
        ],
    )
    def test_assorted_formats(self, description: str, expected_desc: str, n: int, m: int) -> None:
        result = parse_installment(description)
        assert result.clean_description == expected_desc
        assert result.installment_number == n
        assert result.installment_count == m
        assert result.is_installment == (m > 1)


class TestParseInstallmentType:
    """Type checks."""

    def test_returns_installment_info(self) -> None:
        result = parse_installment("X (1/2)")
        assert isinstance(result, InstallmentInfo)

    def test_installment_info_is_frozen(self) -> None:
        result = parse_installment("X (1/2)")
        with pytest.raises(AttributeError):
            result.installment_number = 99  # type: ignore[misc]
