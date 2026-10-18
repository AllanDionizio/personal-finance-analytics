"""
Parse the installment notation embedded in transaction descriptions.

The workbooks mark installments with ``(N/M)`` inside the description, where
N is the current installment and M the total. Examples::

    "Telha Norte (7/10)"        → description="Telha Norte", n=7, m=10
    "Amazon (4/4) - Smart Lock" → description="Amazon - Smart Lock", n=4, m=4
    "Mercado"                   → description="Mercado", n=1, m=1, is_installment=False
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Matches ` (N/M) ` anywhere, with the surrounding whitespace.
_INSTALLMENT_RE = re.compile(r"\s*\((\d+)\s*/\s*(\d+)\)\s*")
_WHITESPACE_RE = re.compile(r"\s+")
_DANGLING_DASH_RE = re.compile(r"\s+-\s+-\s+")


@dataclass(frozen=True)
class InstallmentInfo:
    """Result of parsing a transaction description."""

    clean_description: str
    """Description without the ``(N/M)`` tag, whitespace normalized."""

    installment_number: int
    """Current installment (default 1)."""

    installment_count: int
    """Total number of installments (default 1)."""

    is_installment: bool
    """True if ``installment_count > 1``."""


def parse_installment(description: str | None) -> InstallmentInfo:
    """Extract installment info from a description.

    Without a ``(N/M)`` tag, returns installment 1/1 with
    ``is_installment=False`` and the original description, trimmed.

    Args:
        description: transaction description, or None.

    Returns:
        InstallmentInfo with the clean description and installment data.

    Examples:
        >>> parse_installment("Telha Norte (7/10)")
        InstallmentInfo(clean_description='Telha Norte', installment_number=7, installment_count=10, is_installment=True)

        >>> parse_installment("Mercado")
        InstallmentInfo(clean_description='Mercado', installment_number=1, installment_count=1, is_installment=False)

        >>> parse_installment(None)
        InstallmentInfo(clean_description='', installment_number=1, installment_count=1, is_installment=False)
    """
    if description is None:
        return InstallmentInfo("", 1, 1, False)

    text = str(description).strip()
    if not text:
        return InstallmentInfo("", 1, 1, False)

    match = _INSTALLMENT_RE.search(text)
    if not match:
        return InstallmentInfo(text, 1, 1, False)

    n = int(match.group(1))
    m = int(match.group(2))

    # Drop the tag, then normalize whitespace and doubled separators
    cleaned = text[: match.start()] + " " + text[match.end() :]
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    # A tag between two dashes ("A - (1/2) - B") leaves "A - - B"
    cleaned = _DANGLING_DASH_RE.sub(" - ", cleaned)

    return InstallmentInfo(
        clean_description=cleaned,
        installment_number=n,
        installment_count=m,
        is_installment=m > 1,
    )
