"""
Resolve cores de células das planilhas e mapeia pra dimensões de negócio.

As planilhas de origem usam cor de célula como marcador semântico:
- Cor na célula de valor de entrada (col D) codifica o DONO do crédito.
- Cor na célula de descrição/valor de saída (col I ou col valor) codifica
  o MEIO DE PAGAMENTO (cartão usado).

Quirk do Google Sheets: ao exportar XLSX, algumas cores ficam como `rgb`
(hex direto, ex. `FF4BACC6`) e outras como `theme` (referência ao tema do
workbook, ex. `theme=9`). Este módulo unifica os dois casos consultando
o `xl/theme/theme1.xml` quando necessário.

Mapeamento fixado em conversa de design (ver `docs/data-model.md`).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

OOXML_DRAWINGML_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


# --------------------------------------------------------------------------
# Mapeamento canônico (descoberto via inspeção dos XLSX)
# --------------------------------------------------------------------------

#: Hex resolvido (6 chars, sem alpha, uppercase) → dono.
DONO_BY_HEX: dict[str, str] = {
    "4BACC6": "Person A",
    "F79646": "Person B",
    "FFFFFF": "Outros",
    "000000": "Outros",
}

#: Hex resolvido → meio de pagamento.
MEIO_PAGAMENTO_BY_HEX: dict[str, str] = {
    "B4A7D6": "Card A",
    "8E7CC3": "Card B",
}

DONO_DEFAULT = "Outros"
MEIO_PAGAMENTO_DEFAULT = "Outro"


# --------------------------------------------------------------------------
# Paleta do tema
# --------------------------------------------------------------------------


def load_theme_palette(xlsx_path: str | Path) -> list[str | None]:
    """Lê `xl/theme/theme1.xml` do XLSX e retorna a paleta como lista de hex.

    Cada posição da lista corresponde ao índice de tema usado pelas células
    quando `fill.start_color.type == 'theme'`.

    Itens são strings hex de 6 chars (sem alpha, uppercase) ou `None` quando
    a entrada não pôde ser resolvida estaticamente (ex.: cor de sistema sem
    `lastClr`).

    Importante: a ordem dos índices no OOXML não é puramente sequencial —
    `dk1` e `lt1` aparecem **trocados** entre si em relação a `dk2/lt2`
    em alguns templates. Esta função preserva a ordem em que aparecem no
    XML, que é a mesma ordem usada por openpyxl quando reporta
    `start_color.value` para `type='theme'`.

    Args:
        xlsx_path: caminho pra um arquivo .xlsx.

    Returns:
        Lista de strings hex (uppercase, sem alpha) ou None.

    Raises:
        FileNotFoundError: se o xlsx não existe ou não tem `theme1.xml`.
    """
    path = Path(xlsx_path)
    if not path.exists():
        raise FileNotFoundError(f"XLSX não encontrado: {path}")

    with zipfile.ZipFile(path) as z:
        try:
            theme_bytes = z.read("xl/theme/theme1.xml")
        except KeyError as e:
            raise FileNotFoundError(f"theme1.xml ausente em {path}") from e

    tree = ET.fromstring(theme_bytes)
    ns = {"a": OOXML_DRAWINGML_NS}
    scheme = tree.find(".//a:clrScheme", ns)
    if scheme is None:
        return []

    palette: list[str | None] = []
    for entry in scheme:
        srgb = entry.find("a:srgbClr", ns)
        sysclr = entry.find("a:sysClr", ns)
        if srgb is not None:
            palette.append(srgb.attrib["val"].upper())
        elif sysclr is not None:
            last = sysclr.attrib.get("lastClr")
            palette.append(last.upper() if last else None)
        else:
            palette.append(None)

    return palette


# --------------------------------------------------------------------------
# Resolução de cor da célula
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolvedColor:
    """Resultado da resolução de cor de uma célula."""

    hex: str | None
    """Hex normalizado em 6 chars uppercase, ou None se sem cor / não resolvido."""

    source_type: str | None
    """`'rgb'`, `'theme'`, ou None."""

    has_unresolved_tint: bool = False
    """True se a célula tinha `tint != 0`, que este módulo não interpreta."""


def resolve_cell_color(
    cell: Any,
    theme_palette: list[str | None],
) -> ResolvedColor:
    """Resolve a cor de fundo (`fill.start_color`) de uma célula openpyxl.

    Args:
        cell: célula openpyxl (`openpyxl.cell.cell.Cell`).
        theme_palette: paleta retornada por `load_theme_palette` do mesmo workbook.

    Returns:
        ResolvedColor com hex normalizado ou None.

    Notas sobre tint:
        Quando `type='theme'`, OOXML permite um modificador `tint` (-1.0..1.0)
        que escurece (negativo) ou clareia (positivo) a cor base. Nas
        planilhas de origem o tint é sempre 0.0, então este módulo ignora
        e apenas sinaliza via `has_unresolved_tint=True` se encontrar tint
        diferente de zero (pra debug futuro).
    """
    if cell is None or cell.fill is None:
        return ResolvedColor(None, None)

    color = cell.fill.start_color
    if color is None:
        return ResolvedColor(None, None)

    tint = getattr(color, "tint", 0.0) or 0.0
    has_tint = abs(tint) > 1e-6

    if color.type == "rgb":
        value = color.value
        if value is None:
            return ResolvedColor(None, "rgb", has_tint)
        hex_value = str(value).upper()
        # Remover canal alpha quando presente (FFRRGGBB → RRGGBB)
        if len(hex_value) == 8:
            hex_value = hex_value[2:]
        elif len(hex_value) != 6:
            return ResolvedColor(None, "rgb", has_tint)
        return ResolvedColor(hex_value, "rgb", has_tint)

    if color.type == "theme":
        try:
            idx = int(color.value)
        except (TypeError, ValueError):
            return ResolvedColor(None, "theme", has_tint)
        if 0 <= idx < len(theme_palette):
            return ResolvedColor(theme_palette[idx], "theme", has_tint)
        return ResolvedColor(None, "theme", has_tint)

    # type='indexed', 'auto' etc — não usados nos arquivos de origem
    return ResolvedColor(None, color.type, has_tint)


# --------------------------------------------------------------------------
# Mapeamento hex → dimensão de negócio
# --------------------------------------------------------------------------


def dono_from_hex(hex_color: str | None) -> str:
    """Mapeia hex resolvido pra dono. Retorna `'Outros'` se não reconhecer.

    Aceita None e qualquer caso (lowercase / uppercase / com ou sem `#`).
    """
    if hex_color is None:
        return DONO_DEFAULT
    normalized = hex_color.lstrip("#").upper()
    return DONO_BY_HEX.get(normalized, DONO_DEFAULT)


def meio_pagamento_from_hex(hex_color: str | None) -> str:
    """Mapeia hex resolvido pra meio de pagamento. Retorna `'Outro'` se não reconhecer.

    Aceita None e qualquer caso.
    """
    if hex_color is None:
        return MEIO_PAGAMENTO_DEFAULT
    normalized = hex_color.lstrip("#").upper()
    return MEIO_PAGAMENTO_BY_HEX.get(normalized, MEIO_PAGAMENTO_DEFAULT)


def resolve_dono(cell: Any, theme_palette: list[str | None]) -> str:
    """Atalho: célula → dono. Combina `resolve_cell_color` + `dono_from_hex`."""
    return dono_from_hex(resolve_cell_color(cell, theme_palette).hex)


def resolve_meio_pagamento(cell: Any, theme_palette: list[str | None]) -> str:
    """Atalho: célula → meio de pagamento."""
    return meio_pagamento_from_hex(resolve_cell_color(cell, theme_palette).hex)
