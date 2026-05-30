"""
Parser pra notação de parcela embutida em descrições de transações.

As planilhas usam a convenção `(N/M)` na string de descrição pra marcar
parcelas, onde N é a parcela atual e M é o total. Exemplos::

    "Telha Norte (7/10)"        → desc="Telha Norte", n=7, m=10
    "Amazon (4/4) - Smart Lock" → desc="Amazon - Smart Lock", n=4, m=4
    "Mercado"                   → desc="Mercado", n=1, m=1, eh_parcelada=False
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Captura ` (N/M) ` em qualquer posição. Não-greedy nas bordas pra não comer
# espaços demais.
_PARCELA_RE = re.compile(r"\s*\((\d+)\s*/\s*(\d+)\)\s*")
_WHITESPACE_RE = re.compile(r"\s+")
_DANGLING_DASH_RE = re.compile(r"\s+-\s+-\s+")


@dataclass(frozen=True)
class ParcelaInfo:
    """Resultado de parsear uma descrição de transação."""

    descricao_limpa: str
    """Descrição sem o sufixo `(N/M)`, com espaços normalizados."""

    parcela_num: int
    """Número da parcela atual (default 1)."""

    parcela_total: int
    """Total de parcelas (default 1)."""

    eh_parcelada: bool
    """True se `parcela_total > 1`."""


def parse_parcela(descricao: str | None) -> ParcelaInfo:
    """Extrai informação de parcela de uma descrição.

    Se nenhuma notação `(N/M)` for encontrada, retorna parcela 1/1 com
    `eh_parcelada=False` e descrição original (limpa de espaços).

    Args:
        descricao: string de descrição da transação, ou None.

    Returns:
        ParcelaInfo com descrição limpa e dados de parcela.

    Examples:
        >>> parse_parcela("Telha Norte (7/10)")
        ParcelaInfo(descricao_limpa='Telha Norte', parcela_num=7, parcela_total=10, eh_parcelada=True)

        >>> parse_parcela("Mercado")
        ParcelaInfo(descricao_limpa='Mercado', parcela_num=1, parcela_total=1, eh_parcelada=False)

        >>> parse_parcela(None)
        ParcelaInfo(descricao_limpa='', parcela_num=1, parcela_total=1, eh_parcelada=False)
    """
    if descricao is None:
        return ParcelaInfo("", 1, 1, False)

    text = str(descricao).strip()
    if not text:
        return ParcelaInfo("", 1, 1, False)

    match = _PARCELA_RE.search(text)
    if not match:
        return ParcelaInfo(text, 1, 1, False)

    n = int(match.group(1))
    m = int(match.group(2))

    # Remove a parcela; normaliza espaços e separadores duplicados
    cleaned = text[: match.start()] + " " + text[match.end() :]
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    # Caso a parcela estivesse entre dois traços (ex.: "A - (1/2) - B") fica "A - - B"
    cleaned = _DANGLING_DASH_RE.sub(" - ", cleaned)

    return ParcelaInfo(
        descricao_limpa=cleaned,
        parcela_num=n,
        parcela_total=m,
        eh_parcelada=m > 1,
    )
