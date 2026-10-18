"""
Resolve spreadsheet cell colors and map them to business dimensions.

The source workbooks use cell background color as meaning:

- The color of a credit's amount cell (column D) encodes the **owner**.
- The color of a debit's description or amount cell encodes the
  **payment method** (which card was used).

Google Sheets quirk: when exported to XLSX, some fills are stored as ``rgb``
(a literal hex such as ``FF4BACC6``) and others as ``theme`` (an index into
the workbook theme, such as ``theme=9``). This module resolves both by
reading ``xl/theme/theme1.xml`` when needed.

The mapping is documented in ``docs/data-model.md``.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

OOXML_DRAWINGML_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


# --------------------------------------------------------------------------
# Canonical mapping (found by inspecting the workbooks)
# --------------------------------------------------------------------------

#: Resolved hex (6 chars, no alpha, uppercase) → owner.
OWNER_BY_HEX: dict[str, str] = {
    "4BACC6": "Person A",
    "F79646": "Person B",
    "FFFFFF": "Other",
    "000000": "Other",
}

#: Resolved hex → payment method.
PAYMENT_METHOD_BY_HEX: dict[str, str] = {
    "B4A7D6": "Card A",
    "8E7CC3": "Card B",
    "9FC5E8": "Card C",
}

OWNER_DEFAULT = "Other"
PAYMENT_METHOD_DEFAULT = "Other"


# --------------------------------------------------------------------------
# Theme palette
# --------------------------------------------------------------------------


def load_theme_palette(xlsx_path: str | Path) -> list[str | None]:
    """Read ``xl/theme/theme1.xml`` from the XLSX and return its palette as hex.

    Each position matches the theme index cells use when
    ``fill.start_color.type == 'theme'``.

    Items are 6-char hex strings (no alpha, uppercase), or ``None`` when an
    entry can't be resolved statically (e.g. a system color without
    ``lastClr``).

    Note: OOXML index order is not purely sequential; in some templates
    ``dk1``/``lt1`` are swapped relative to ``dk2``/``lt2``. This function
    keeps the order of the XML, which is the order openpyxl uses when it
    reports ``start_color.value`` for ``type='theme'``.

    Args:
        xlsx_path: path to an .xlsx file.

    Returns:
        List of hex strings (uppercase, no alpha) or None.

    Raises:
        FileNotFoundError: if the xlsx doesn't exist or has no ``theme1.xml``.
    """
    path = Path(xlsx_path)
    if not path.exists():
        raise FileNotFoundError(f"XLSX not found: {path}")

    with zipfile.ZipFile(path) as z:
        try:
            theme_bytes = z.read("xl/theme/theme1.xml")
        except KeyError as e:
            raise FileNotFoundError(f"theme1.xml missing in {path}") from e

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
# Cell color resolution
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolvedColor:
    """Result of resolving a cell's color."""

    hex: str | None
    """Normalized 6-char uppercase hex, or None if no color / unresolved."""

    source_type: str | None
    """``'rgb'``, ``'theme'``, or None."""

    has_unresolved_tint: bool = False
    """True if the cell had ``tint != 0``, which this module doesn't apply."""


def resolve_cell_color(
    cell: Any,
    theme_palette: list[str | None],
) -> ResolvedColor:
    """Resolve the background color (``fill.start_color``) of an openpyxl cell.

    Args:
        cell: openpyxl cell (``openpyxl.cell.cell.Cell``).
        theme_palette: palette from ``load_theme_palette`` for the same workbook.

    Returns:
        ResolvedColor with a normalized hex, or None.

    Note on tint:
        With ``type='theme'``, OOXML allows a ``tint`` modifier (-1.0..1.0)
        that darkens (negative) or lightens (positive) the base color. The
        source workbooks always use tint 0.0, so this module ignores it and
        only flags a non-zero tint via ``has_unresolved_tint=True``.
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
        # Drop the alpha channel when present (FFRRGGBB → RRGGBB)
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

    # type='indexed', 'auto' etc. are not used in the source files
    return ResolvedColor(None, color.type, has_tint)


# --------------------------------------------------------------------------
# Hex → business dimension
# --------------------------------------------------------------------------


def owner_from_hex(hex_color: str | None) -> str:
    """Map a resolved hex to an owner; ``'Other'`` if unknown.

    Accepts None and any case, with or without ``#``.
    """
    if hex_color is None:
        return OWNER_DEFAULT
    normalized = hex_color.lstrip("#").upper()
    return OWNER_BY_HEX.get(normalized, OWNER_DEFAULT)


def payment_method_from_hex(hex_color: str | None) -> str:
    """Map a resolved hex to a payment method; ``'Other'`` if unknown.

    Accepts None and any case, with or without ``#``.
    """
    if hex_color is None:
        return PAYMENT_METHOD_DEFAULT
    normalized = hex_color.lstrip("#").upper()
    return PAYMENT_METHOD_BY_HEX.get(normalized, PAYMENT_METHOD_DEFAULT)


def resolve_owner(cell: Any, theme_palette: list[str | None]) -> str:
    """Shortcut: cell → owner. Combines ``resolve_cell_color`` + ``owner_from_hex``."""
    return owner_from_hex(resolve_cell_color(cell, theme_palette).hex)


def resolve_payment_method(cell: Any, theme_palette: list[str | None]) -> str:
    """Shortcut: cell → payment method."""
    return payment_method_from_hex(resolve_cell_color(cell, theme_palette).hex)
