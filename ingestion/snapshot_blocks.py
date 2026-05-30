"""
Detector de blocos da aba "Situação Atual".

A aba é estruturada como blocos empilhados, cada um representando um
snapshot da carteira em uma `Data Referência` específica. Estrutura típica
de cada bloco::

    Linha N:    ... | Data Referência: | 2026-05-23 | ...
    Linha N+1:  Banco/Corretora | Aplicação | Valor Bruto | Alocação | ...
    Linha N+2+: <linhas de dados>
    (linha em branco até o próximo bloco)

Headers e número de colunas variam entre snapshots (foram sendo adicionados
ao longo dos anos), por isso o detector resolve cada header dinamicamente
buscando nomes canônicos.

Exemplo de uso::

    wb = load_workbook("data/raw/2026.xlsx", data_only=True)
    ws = wb["Situação Atual"]
    for block in find_snapshot_blocks(ws):
        for row in iter_snapshot_rows(ws, block):
            print(block.data_referencia, row)
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

# Marcador que identifica início de cada bloco
DATA_REFERENCIA_MARKER = "Data Referência"

# Range de colunas onde a tabela de carteira pode estar.
# As colunas M+ contêm informação acessória (parcelas pendentes etc.) que
# não pertence ao snapshot da carteira, então limitamos a busca aqui.
CARTEIRA_MIN_COL = 1  # A
CARTEIRA_MAX_COL = 12  # L (12 colunas)


# Mapeamento header observado → nome canônico
# (chave em lowercase, sem acentos críticos pra robustez — comparação
# usa _normalize)
_HEADER_SYNONYMS: dict[str, str] = {
    "banco/corretora": "banco_corretora",
    "banco / corretora": "banco_corretora",
    "banco": "banco_corretora",
    "corretora": "banco_corretora",
    "aplicação": "aplicacao",
    "aplicacao": "aplicacao",
    "ativo": "aplicacao",
    "valor bruto": "valor_bruto",
    "valor": "valor_bruto",
    "valor atual": "valor_bruto",
    "alocação": "alocacao_pct",
    "alocacao": "alocacao_pct",
    "% alocação": "alocacao_pct",
    "% alocacao": "alocacao_pct",
    "vencimento": "vencimento",
    "mom": "mom",
    "m/m": "mom",
    "yoy": "yoy",
    "y/y": "yoy",
    "valor líquido final": "valor_liquido_final",
    "valor liquido final": "valor_liquido_final",
    "rendimento atual": "rendimento_atual",
    "rendimento final": "rendimento_final",
}


@dataclass
class SnapshotBlock:
    """Localização de um bloco de snapshot dentro da aba."""

    data_referencia: date
    """Data extraída do marcador `Data Referência:`."""

    marker_row: int
    """Linha (1-based) onde está o marcador."""

    header_row: int | None
    """Linha do header das colunas (1-based) ou None se sem header (snapshot textual)."""

    end_row: int
    """Última linha pertencente a este bloco (exclusiva — primeira linha que NÃO faz parte)."""

    header_map: dict[str, int] = field(default_factory=dict)
    """Nome canônico de coluna → índice de coluna (1-based)."""


def find_snapshot_blocks(ws: Any) -> list[SnapshotBlock]:
    """Encontra todos os blocos de snapshot numa worksheet.

    Args:
        ws: worksheet do openpyxl (geralmente `wb["Situação Atual"]`).

    Returns:
        Lista de SnapshotBlock em ordem (do mais antigo ao mais recente).
        Blocos sem header detectável (ex.: o primeiro snapshot que muitas
        vezes é só texto-resumo) são retornados com `header_row=None` e
        `header_map={}` — podem ser pulados pelo consumidor.
    """
    # Passo 1: localizar todas as linhas com marcador "Data Referência"
    markers: list[tuple[int, int, date]] = []
    for row in ws.iter_rows():
        for cell in row:
            value = cell.value
            if value is not None and DATA_REFERENCIA_MARKER in str(value):
                ref_date = _find_reference_date(ws, cell.row, cell.column)
                if ref_date is not None:
                    markers.append((cell.row, cell.column, ref_date))
                break  # um marcador por linha basta

    if not markers:
        return []

    # Passo 2: pra cada marcador, identificar header e fim do bloco
    blocks: list[SnapshotBlock] = []
    for i, (marker_row, _marker_col, ref_date) in enumerate(markers):
        end_row = markers[i + 1][0] if i + 1 < len(markers) else ws.max_row + 1

        header_row, header_map = _find_header_row(ws, marker_row + 1, end_row)
        blocks.append(
            SnapshotBlock(
                data_referencia=ref_date,
                marker_row=marker_row,
                header_row=header_row,
                end_row=end_row,
                header_map=header_map,
            )
        )

    return blocks


def iter_snapshot_rows(ws: Any, block: SnapshotBlock) -> Iterator[dict[str, Any]]:
    """Itera as linhas de dados de um bloco como dicts com nomes canônicos.

    Pula linhas vazias e linhas de totalização (que começam com "Total"
    ou similares).

    Args:
        ws: worksheet.
        block: SnapshotBlock retornado por `find_snapshot_blocks`.

    Yields:
        dict {nome_canonico: valor} pra cada linha de dado.
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

        # Filtra linhas de totalização (ex.: "Total:" na primeira coluna)
        first_col_value = ws.cell(row, min(block.header_map.values())).value
        if first_col_value and "total" in str(first_col_value).lower():
            continue

        yield record


# --------------------------------------------------------------------------
# Helpers internos
# --------------------------------------------------------------------------


def _find_reference_date(ws: Any, row: int, marker_col: int) -> date | None:
    """Procura a data de referência adjacente ao marcador.

    O marcador "Data Referência:" geralmente fica numa célula e a data
    numa célula imediatamente à direita. Vasculha até 5 colunas adiante.
    """
    for col_offset in range(1, 6):
        cell = ws.cell(row, marker_col + col_offset)
        if cell.value is None:
            continue
        if isinstance(cell.value, datetime):
            return cell.value.date()
        if isinstance(cell.value, date):
            return cell.value
        # Tentativa best-effort de parsing de string
        text = str(cell.value).strip()
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
    return None


def _find_header_row(ws: Any, start: int, end: int) -> tuple[int | None, dict[str, int]]:
    """Encontra a primeira linha do range com pelo menos 2 headers canônicos.

    Returns:
        (linha_do_header, dict {nome_canonico: col_index}) ou (None, {}).
    """
    for row in range(start, end):
        header_map: dict[str, int] = {}
        for col in range(CARTEIRA_MIN_COL, CARTEIRA_MAX_COL + 1):
            cell_value = ws.cell(row, col).value
            canonical = _match_header(cell_value)
            if canonical and canonical not in header_map:
                header_map[canonical] = col
        if len(header_map) >= 2:
            return row, header_map
    return None, {}


def _match_header(value: Any) -> str | None:
    """Casa um valor de célula contra os sinônimos de header conhecidos."""
    if value is None:
        return None
    key = _normalize(str(value))
    if not key:
        return None
    return _HEADER_SYNONYMS.get(key)


def _normalize(text: str) -> str:
    """Lowercase + collapse de espaços, sem alterar acentos."""
    return " ".join(text.strip().lower().split())
