"""Testes do snapshot_blocks. Requer XLSX real como fixture."""

from __future__ import annotations

import itertools
from datetime import date
from pathlib import Path

import pytest
from openpyxl import load_workbook

from ingestion.snapshot_blocks import (
    SnapshotBlock,
    find_snapshot_blocks,
    iter_snapshot_rows,
)


@pytest.fixture(scope="module")
def situacao_atual(fixture_xlsx_path: Path):
    """Worksheet 'Situação Atual' do XLSX fixture."""
    wb = load_workbook(fixture_xlsx_path, data_only=True)
    return wb["Situação Atual"]


class TestFindSnapshotBlocks:
    def test_encontra_blocos(self, situacao_atual) -> None:
        blocks = find_snapshot_blocks(situacao_atual)
        assert len(blocks) > 0

    def test_blocos_em_ordem_cronologica(self, situacao_atual) -> None:
        blocks = find_snapshot_blocks(situacao_atual)
        dates = [b.data_referencia for b in blocks]
        assert dates == sorted(dates), "Blocos não estão em ordem cronológica"

    def test_todos_blocos_tem_data(self, situacao_atual) -> None:
        blocks = find_snapshot_blocks(situacao_atual)
        for block in blocks:
            assert isinstance(block.data_referencia, date)

    def test_marker_e_end_consistentes(self, situacao_atual) -> None:
        """end_row > marker_row sempre."""
        blocks = find_snapshot_blocks(situacao_atual)
        for block in blocks:
            assert block.end_row > block.marker_row

    def test_blocos_nao_se_sobrepoem(self, situacao_atual) -> None:
        """end_row de um bloco <= marker_row do próximo."""
        blocks = find_snapshot_blocks(situacao_atual)
        for prev, curr in itertools.pairwise(blocks):
            assert prev.end_row <= curr.marker_row


class TestHeaderDetection:
    def test_blocos_modernos_tem_header(self, situacao_atual) -> None:
        """Snapshots de 2022+ devem ter header detectado."""
        blocks = find_snapshot_blocks(situacao_atual)
        # Pelo menos um bloco precisa ter header (qualquer um a partir de 2022-09)
        com_header = [b for b in blocks if b.header_row is not None]
        assert len(com_header) > 0

    def test_header_contem_banco_corretora_e_aplicacao(self, situacao_atual) -> None:
        """Headers reconhecidos devem incluir pelo menos banco_corretora e aplicacao."""
        blocks = find_snapshot_blocks(situacao_atual)
        for block in blocks:
            if block.header_row is None:
                continue
            assert "banco_corretora" in block.header_map
            assert "aplicacao" in block.header_map
            assert "valor_bruto" in block.header_map

    def test_header_evolui_ao_longo_do_tempo(self, situacao_atual) -> None:
        """Snapshots recentes têm mais colunas que os antigos."""
        blocks = [b for b in find_snapshot_blocks(situacao_atual) if b.header_row is not None]
        if len(blocks) < 5:
            pytest.skip("Não há snapshots suficientes pra testar evolução")
        primeiros = blocks[:3]
        ultimos = blocks[-3:]
        media_antiga = sum(len(b.header_map) for b in primeiros) / len(primeiros)
        media_recente = sum(len(b.header_map) for b in ultimos) / len(ultimos)
        assert media_recente > media_antiga


class TestIterSnapshotRows:
    def test_itera_linhas_com_dados(self, situacao_atual) -> None:
        """Algum bloco moderno deve render pelo menos 1 linha de dado."""
        blocks = [b for b in find_snapshot_blocks(situacao_atual) if b.header_row is not None]
        assert blocks, "Nenhum bloco com header — fixture inadequado"

        # Pegar o último bloco (mais completo)
        ultimo = blocks[-1]
        rows = list(iter_snapshot_rows(situacao_atual, ultimo))
        assert len(rows) > 0

    def test_linhas_contem_chaves_canonicas(self, situacao_atual) -> None:
        blocks = [b for b in find_snapshot_blocks(situacao_atual) if b.header_row is not None]
        ultimo = blocks[-1]
        rows = list(iter_snapshot_rows(situacao_atual, ultimo))
        for row in rows:
            assert "banco_corretora" in row or "aplicacao" in row

    def test_pula_linhas_vazias(self, situacao_atual) -> None:
        """Nenhuma linha devolvida deve ter TODAS as colunas vazias."""
        blocks = [b for b in find_snapshot_blocks(situacao_atual) if b.header_row is not None]
        for block in blocks[:5]:  # primeiros 5 por performance
            for row in iter_snapshot_rows(situacao_atual, block):
                tem_valor = any(v is not None and str(v).strip() != "" for v in row.values())
                assert tem_valor

    def test_bloco_sem_header_nao_yield(self, situacao_atual) -> None:
        """Blocos sem header detectado não devem produzir linhas."""
        bloco_fake = SnapshotBlock(
            data_referencia=date(2020, 1, 1),
            marker_row=1,
            header_row=None,
            end_row=10,
            header_map={},
        )
        rows = list(iter_snapshot_rows(situacao_atual, bloco_fake))
        assert rows == []


class TestRegressao:
    """Casos específicos observados no XLSX 2026."""

    def test_snapshot_2026_05_23_existe(self, situacao_atual) -> None:
        """O último snapshot conhecido é 2026-05-23."""
        blocks = find_snapshot_blocks(situacao_atual)
        datas = [b.data_referencia for b in blocks]
        assert date(2026, 5, 23) in datas

    def test_snapshot_2022_08_25_existe(self, situacao_atual) -> None:
        """O primeiro snapshot conhecido é 2022-08-25."""
        blocks = find_snapshot_blocks(situacao_atual)
        datas = [b.data_referencia for b in blocks]
        assert date(2022, 8, 25) in datas
