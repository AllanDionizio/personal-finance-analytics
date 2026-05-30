"""Libs de ingestão dos XLSX de origem."""

from ingestion.color_resolver import (
    DONO_BY_HEX,
    MEIO_PAGAMENTO_BY_HEX,
    ResolvedColor,
    dono_from_hex,
    load_theme_palette,
    meio_pagamento_from_hex,
    resolve_cell_color,
    resolve_dono,
    resolve_meio_pagamento,
)
from ingestion.parcela_parser import ParcelaInfo, parse_parcela
from ingestion.snapshot_blocks import (
    SnapshotBlock,
    find_snapshot_blocks,
    iter_snapshot_rows,
)

__all__ = [
    # color_resolver
    "DONO_BY_HEX",
    "MEIO_PAGAMENTO_BY_HEX",
    # parcela_parser
    "ParcelaInfo",
    "ResolvedColor",
    # snapshot_blocks
    "SnapshotBlock",
    "dono_from_hex",
    "find_snapshot_blocks",
    "iter_snapshot_rows",
    "load_theme_palette",
    "meio_pagamento_from_hex",
    "parse_parcela",
    "resolve_cell_color",
    "resolve_dono",
    "resolve_meio_pagamento",
]
