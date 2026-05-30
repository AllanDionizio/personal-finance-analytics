"""Testes do color_resolver.

Inclui testes puros pra `dono_from_hex` / `meio_pagamento_from_hex` e
testes de integração que requerem um XLSX real como fixture.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ingestion.color_resolver import (
    DONO_BY_HEX,
    DONO_DEFAULT,
    MEIO_PAGAMENTO_BY_HEX,
    MEIO_PAGAMENTO_DEFAULT,
    dono_from_hex,
    load_theme_palette,
    meio_pagamento_from_hex,
    resolve_cell_color,
    resolve_dono,
    resolve_meio_pagamento,
)

# --------------------------------------------------------------------------
# Testes puros
# --------------------------------------------------------------------------


class TestDonoFromHex:
    """Mapeamento de hex pra dono."""

    @pytest.mark.parametrize(
        "hex_color,esperado",
        [
            ("4BACC6", "Person A"),
            ("F79646", "Person B"),
            ("FFFFFF", "Outros"),
            ("000000", "Outros"),
        ],
    )
    def test_cores_conhecidas(self, hex_color: str, esperado: str) -> None:
        assert dono_from_hex(hex_color) == esperado

    def test_case_insensitive(self) -> None:
        assert dono_from_hex("4bacc6") == "Person A"
        assert dono_from_hex("4BaCc6") == "Person A"

    def test_com_prefixo_hash(self) -> None:
        assert dono_from_hex("#4BACC6") == "Person A"
        assert dono_from_hex("#f79646") == "Person B"

    def test_cor_desconhecida_retorna_default(self) -> None:
        assert dono_from_hex("ABCDEF") == DONO_DEFAULT

    def test_none_retorna_default(self) -> None:
        assert dono_from_hex(None) == DONO_DEFAULT

    def test_mapeamento_canonico_contem_dimensoes_esperadas(self) -> None:
        """Sanity check: os valores únicos do mapeamento são os esperados."""
        assert set(DONO_BY_HEX.values()) == {"Person A", "Person B", "Outros"}


class TestMeioPagamentoFromHex:
    """Mapeamento de hex pra meio de pagamento."""

    @pytest.mark.parametrize(
        "hex_color,esperado",
        [
            ("B4A7D6", "Card A"),
            ("8E7CC3", "Card B"),
            ("b4a7d6", "Card A"),
            ("#8e7cc3", "Card B"),
        ],
    )
    def test_cores_conhecidas(self, hex_color: str, esperado: str) -> None:
        assert meio_pagamento_from_hex(hex_color) == esperado

    def test_cor_desconhecida_retorna_default(self) -> None:
        assert meio_pagamento_from_hex("ABCDEF") == MEIO_PAGAMENTO_DEFAULT

    def test_none_retorna_default(self) -> None:
        assert meio_pagamento_from_hex(None) == MEIO_PAGAMENTO_DEFAULT

    def test_mapeamento_canonico(self) -> None:
        assert set(MEIO_PAGAMENTO_BY_HEX.values()) == {"Card A", "Card B"}


# --------------------------------------------------------------------------
# Testes de integração — requer XLSX real
# --------------------------------------------------------------------------


class TestThemePalette:
    """Lê a paleta do tema do XLSX real."""

    def test_paleta_tem_12_entradas(self, fixture_xlsx_path: Path) -> None:
        palette = load_theme_palette(fixture_xlsx_path)
        # OOXML padrão tem 12 cores no clrScheme
        assert len(palette) == 12

    def test_paleta_contem_accent5_person_a(self, fixture_xlsx_path: Path) -> None:
        """Accent5 (índice 8) deve ser o teal usado pra Person A."""
        palette = load_theme_palette(fixture_xlsx_path)
        assert palette[8] == "4BACC6"

    def test_paleta_contem_accent6_person_b(self, fixture_xlsx_path: Path) -> None:
        """Accent6 (índice 9) deve ser o laranja usado pra Person B."""
        palette = load_theme_palette(fixture_xlsx_path)
        assert palette[9] == "F79646"

    def test_paleta_arquivo_inexistente(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_theme_palette("/tmp/nao_existe_zzz.xlsx")


class TestResolveCellColorReal:
    """Resolve cor em células reais usando openpyxl."""

    @pytest.fixture(scope="class")
    def ws_jan(self, fixture_xlsx_path: Path):
        from openpyxl import load_workbook

        wb = load_workbook(fixture_xlsx_path, data_only=True)
        return wb["JAN"]

    @pytest.fixture(scope="class")
    def palette(self, fixture_xlsx_path: Path) -> list[str | None]:
        return load_theme_palette(fixture_xlsx_path)

    def test_resolve_cor_rgb_direto(self, ws_jan, palette) -> None:
        """D19 (entrada de Person A) deve resolver como rgb FF4BACC6 → 4BACC6."""
        cell = ws_jan.cell(19, 4)
        result = resolve_cell_color(cell, palette)
        assert result.hex == "4BACC6"
        assert result.source_type == "rgb"

    def test_resolve_cor_theme(self, ws_jan, palette) -> None:
        """D26 (entrada de Person B) usa theme=9 — deve resolver como F79646."""
        cell = ws_jan.cell(26, 4)
        result = resolve_cell_color(cell, palette)
        assert result.hex == "F79646"
        assert result.source_type == "theme"

    def test_resolve_dono_de_celula(self, ws_jan, palette) -> None:
        """Atalhos resolve_dono e resolve_meio_pagamento funcionam end-to-end."""
        # D19 → Person A
        assert resolve_dono(ws_jan.cell(19, 4), palette) == "Person A"
        # D26 → Person B (via theme)
        assert resolve_dono(ws_jan.cell(26, 4), palette) == "Person B"

    def test_resolve_nubank_de_saida(self, ws_jan, palette) -> None:
        """Saídas (col L) com cor B4A7D6 devem mapear como Card A."""
        # Procurar uma célula com Card A — pegar a primeira linha de saída
        for row in range(19, 100):
            cell = ws_jan.cell(row, 12)  # col L
            if cell.value is None:
                continue
            color = resolve_cell_color(cell, palette)
            if color.hex == "B4A7D6":
                assert resolve_meio_pagamento(cell, palette) == "Card A"
                return
        pytest.fail("Nenhuma célula com cor de Card A encontrada em JAN")
