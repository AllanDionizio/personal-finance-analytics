"""Testes do parcela_parser. Testes puros, sem fixtures externas."""

from __future__ import annotations

import pytest

from ingestion.parcela_parser import ParcelaInfo, parse_parcela


class TestParseParcelaBasico:
    """Casos básicos: sem parcela, com parcela no final, vazios."""

    def test_sem_parcela(self) -> None:
        result = parse_parcela("Mercado")
        assert result == ParcelaInfo("Mercado", 1, 1, False)

    def test_parcela_no_final(self) -> None:
        result = parse_parcela("Telha Norte (7/10)")
        assert result == ParcelaInfo("Telha Norte", 7, 10, True)

    def test_descricao_vazia(self) -> None:
        result = parse_parcela("")
        assert result == ParcelaInfo("", 1, 1, False)

    def test_descricao_none(self) -> None:
        result = parse_parcela(None)
        assert result == ParcelaInfo("", 1, 1, False)

    def test_apenas_espacos(self) -> None:
        result = parse_parcela("   ")
        assert result == ParcelaInfo("", 1, 1, False)


class TestParseParcelaPosicoes:
    """Casos onde (N/M) aparece em posições diferentes da descrição."""

    def test_parcela_no_meio(self) -> None:
        result = parse_parcela("Amazon (4/4) - Smart Lock")
        assert result.descricao_limpa == "Amazon - Smart Lock"
        assert result.parcela_num == 4
        assert result.parcela_total == 4
        assert result.eh_parcelada is True

    def test_parcela_no_comeco(self) -> None:
        result = parse_parcela("(1/12) Compra Mac")
        assert result.descricao_limpa == "Compra Mac"
        assert result.parcela_num == 1
        assert result.parcela_total == 12

    def test_parcela_com_espacos_extras(self) -> None:
        result = parse_parcela("Item   (2/3)   ")
        assert result.descricao_limpa == "Item"
        assert result.parcela_num == 2
        assert result.parcela_total == 3

    def test_parcela_com_espaco_interno(self) -> None:
        # Tolerância: "(2 / 3)" e "(2/ 3)" devem funcionar
        result = parse_parcela("Item (2 / 3)")
        assert result.parcela_num == 2
        assert result.parcela_total == 3


class TestParseParcelaCasos:
    """Casos de borda e variações."""

    def test_parcela_unica_nao_eh_parcelada(self) -> None:
        """(1/1) significa "à vista" — não é considerada parcelada."""
        result = parse_parcela("Item (1/1)")
        assert result.parcela_num == 1
        assert result.parcela_total == 1
        assert result.eh_parcelada is False

    def test_apenas_parcela(self) -> None:
        """String que é só `(N/M)` deve retornar descrição vazia."""
        result = parse_parcela("(3/5)")
        assert result.descricao_limpa == ""
        assert result.parcela_num == 3
        assert result.parcela_total == 5

    def test_acentos_preservados(self) -> None:
        result = parse_parcela("Mecânica do João (2/6)")
        assert result.descricao_limpa == "Mecânica do João"

    def test_numero_no_meio_da_descricao_nao_eh_parcela(self) -> None:
        """`10/12` sem parênteses não é parcela."""
        result = parse_parcela("Café Sabor 10/12 Premium")
        assert result.descricao_limpa == "Café Sabor 10/12 Premium"
        assert result.eh_parcelada is False

    @pytest.mark.parametrize(
        "descricao,esperado_desc,n,m",
        [
            ("Aquacenter (10/12)", "Aquacenter", 10, 12),
            ("Casa  (6/24)  Item", "Casa Item", 6, 24),
            ("X-Y-Z (1/3)", "X-Y-Z", 1, 3),
            ("Detalhe (12/48) — anotação", "Detalhe — anotação", 12, 48),
        ],
    )
    def test_diversos_formatos(self, descricao: str, esperado_desc: str, n: int, m: int) -> None:
        result = parse_parcela(descricao)
        assert result.descricao_limpa == esperado_desc
        assert result.parcela_num == n
        assert result.parcela_total == m
        assert result.eh_parcelada == (m > 1)


class TestParseParcelaTipo:
    """Validações de tipo."""

    def test_retorna_parcela_info(self) -> None:
        result = parse_parcela("X (1/2)")
        assert isinstance(result, ParcelaInfo)

    def test_parcela_info_imutavel(self) -> None:
        """ParcelaInfo é frozen — não pode setar atributo."""
        result = parse_parcela("X (1/2)")
        with pytest.raises(AttributeError):
            result.parcela_num = 99  # type: ignore[misc]
