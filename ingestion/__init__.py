"""Ingestion libraries for the source workbooks."""

from ingestion.color_resolver import (
    OWNER_BY_HEX,
    PAYMENT_METHOD_BY_HEX,
    ResolvedColor,
    load_theme_palette,
    owner_from_hex,
    payment_method_from_hex,
    resolve_cell_color,
    resolve_owner,
    resolve_payment_method,
)
from ingestion.installment_parser import InstallmentInfo, parse_installment
from ingestion.snapshot_blocks import (
    SnapshotBlock,
    find_snapshot_blocks,
    iter_snapshot_rows,
)

__all__ = [
    "OWNER_BY_HEX",
    "PAYMENT_METHOD_BY_HEX",
    "InstallmentInfo",
    "ResolvedColor",
    "SnapshotBlock",
    "find_snapshot_blocks",
    "iter_snapshot_rows",
    "load_theme_palette",
    "owner_from_hex",
    "parse_installment",
    "payment_method_from_hex",
    "resolve_cell_color",
    "resolve_owner",
    "resolve_payment_method",
]
