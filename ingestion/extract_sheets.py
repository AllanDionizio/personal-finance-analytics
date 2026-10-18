"""
Orquestra a extração literal dos XLSX de origem para a camada `raw.*` do DuckDB.

Lê cada `.xlsx` em `--xlsx-dir` e popula três tabelas:

- ``raw.transacoes``         — uma linha por transação (lado crédito e lado
  débito das abas mensais), com cores de célula preservadas como dados crus.
- ``raw.carteira_snapshots`` — snapshots históricos da aba "Situação Atual".
- ``raw.categorias_config``  — config canônica de categorias (só do arquivo 2026).

Princípios da camada raw (ver ``docs/data-model.md`` seções 2 e 5):

- **Sem transformação**: captura literal, com proveniência (`source_file`,
  `source_sheet`, `source_row`). Limpeza, tipagem forte, parsing de parcela e
  mapeamento de cor → dono/meio_pagamento são responsabilidade do dbt (stg).
  Por isso este módulo **não** usa ``parcela_parser`` (a descrição é gravada
  crua, com o sufixo ``(N/M)``) e usa ``color_resolver`` apenas para *detectar
  e logar* cores não reconhecidas — a resolução final para dimensões de negócio
  acontece em stg.
- **Idempotência**: rerodar sobre o mesmo XLSX produz o mesmo resultado. Cada
  arquivo é recarregado via DELETE-por-`source_file` + INSERT, e o
  `transacao_id` é determinístico (ver ``_transacao_id``).
- **Esquema dinâmico**: as colunas de débito mudam entre 2021 (sem
  MacroCategoria) e 2022+; o header é detectado em runtime, não por posição
  fixa.

CLI::

    python -m ingestion.extract_sheets --xlsx-dir data/raw --db data/warehouse.duckdb
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import duckdb
from openpyxl import load_workbook

from ingestion.color_resolver import (
    DONO_BY_HEX,
    MEIO_PAGAMENTO_BY_HEX,
    load_theme_palette,
    resolve_cell_color,
)
from ingestion.snapshot_blocks import find_snapshot_blocks, iter_snapshot_rows

log = logging.getLogger("ingestion.extract_sheets")

DEFAULT_XLSX_DIR = Path("data/raw")
DEFAULT_DB = Path("data/warehouse.duckdb")

# Arquivo cuja aba "Configurações" é a fonte canônica de categorias.
CONFIG_SOURCE_YEAR = 2026

# Aba "Configurações": colunas e range de linhas (1-based) — ver seção 5.
_CONFIG_ROW_START = 4
_CONFIG_ROW_END = 38  # inclusivo
_CONFIG_COL_RECEITA = 9  # I
_CONFIG_COL_DESPESA = 10  # J
_CONFIG_COL_MACRO = 11  # K
_CONFIG_PLACEHOLDER = "-"  # célula vazia/placeholder a ignorar


# --------------------------------------------------------------------------
# Identificação de abas
# --------------------------------------------------------------------------

_MESES_PREFIX = {
    "jan",
    "fev",
    "mar",
    "abr",
    "mai",
    "jun",
    "jul",
    "ago",
    "set",
    "out",
    "nov",
    "dez",
}


def _is_month_sheet(name: str) -> bool:
    """True se o nome da aba parece um mês (`JAN`, `Fevereiro`, `MAR/26`, ...)."""
    key = name.strip().lower()
    return len(key) >= 3 and key[:3] in _MESES_PREFIX


def _is_situacao_atual(name: str) -> bool:
    key = " ".join(name.strip().lower().split())
    return "situacao atual" in key or "situação atual" in key


def _is_configuracoes(name: str) -> bool:
    return name.strip().lower().startswith("configura")


def _parse_year(filename: str) -> int | None:
    """Extrai o ano (20XX) do nome do arquivo, ex. `2026.xlsx` → 2026."""
    m = re.search(r"(20\d{2})", filename)
    return int(m.group(1)) if m else None


# --------------------------------------------------------------------------
# Detecção de layout das abas mensais (esquema 2021 vs 2022+)
# --------------------------------------------------------------------------

# Header observado (normalizado) → nome canônico de campo.
_MONTH_HEADER_SYNONYMS: dict[str, str] = {
    "descrição": "descricao",
    "descricao": "descricao",
    "categoria": "categoria",
    "categorias": "categoria",
    "macrocategoria": "macrocategoria",
    "macro categoria": "macrocategoria",
    "macro-categoria": "macrocategoria",
    "macro": "macrocategoria",
    "valor": "valor",
    "valores": "valor",
    "data": "data",
    "ok": "status_ok",
    "ok?": "status_ok",
    "status": "status_ok",
    "pago": "status_ok",
}

# Coluna de separação heurística entre o lado crédito (B-G) e o lado débito
# (I-O) quando só um header "Descrição" é encontrado.
_CREDIT_MAX_COL = 7  # G


@dataclass
class MonthLayout:
    """Mapa de colunas detectado para uma aba mensal."""

    header_row: int
    credit: dict[str, int] = field(default_factory=dict)
    debit: dict[str, int] = field(default_factory=dict)


def _match_month_header(value: Any) -> str | None:
    if value is None:
        return None
    key = " ".join(str(value).strip().lower().split())
    return _MONTH_HEADER_SYNONYMS.get(key)


def detect_month_layout(ws: Any) -> MonthLayout | None:
    """Detecta a linha de header e o mapa de colunas crédito/débito.

    Varre as primeiras linhas procurando a que tem mais headers reconhecidos
    (exigindo ao menos `descricao` + `valor`). Os lados crédito e débito são
    separados pela posição da segunda ocorrência de "Descrição": tudo à
    esquerda dela é crédito, o resto é débito. Isso captura dinamicamente o
    deslocamento de colunas entre 2021 (sem MacroCategoria) e 2022+.

    Returns:
        MonthLayout ou None se nenhuma linha de header plausível for achada.
    """
    max_row = min(ws.max_row, 25)
    max_col = min(ws.max_column, 20)
    best: tuple[int, list[tuple[int, str]]] | None = None

    for r in range(1, max_row + 1):
        matches: list[tuple[int, str]] = []
        for c in range(1, max_col + 1):
            canonical = _match_month_header(ws.cell(r, c).value)
            if canonical:
                matches.append((c, canonical))
        canons = {k for _, k in matches}
        has_min = "descricao" in canons and "valor" in canons
        if has_min and (best is None or len(matches) > len(best[1])):
            best = (r, matches)

    if best is None:
        return None

    header_row, matches = best
    desc_cols = sorted(c for c, k in matches if k == "descricao")

    layout = MonthLayout(header_row=header_row)
    if len(desc_cols) >= 2:
        split = desc_cols[-1]  # início do lado débito
        for c, k in matches:
            side = layout.credit if c < split else layout.debit
            side.setdefault(k, c)
    else:
        # Apenas um lado tem header detectável: decide pela posição da coluna.
        target = layout.credit if desc_cols[0] <= _CREDIT_MAX_COL else layout.debit
        for c, k in matches:
            target.setdefault(k, c)

    return layout


# --------------------------------------------------------------------------
# Coerção de valores crus
# --------------------------------------------------------------------------

_NULLISH = {"", "-", "n/a", "na"}


def _to_str(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
    s = str(value).strip()
    if s.lower() in _NULLISH:
        return None
    s = s.replace("R$", "").replace("%", "").replace(" ", "").replace("\xa0", "")
    # pt-BR "1.234,56" → "1234.56"
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _to_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if s.lower() in _NULLISH:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


# --------------------------------------------------------------------------
# Cores cruas + rastreio de cores não reconhecidas
# --------------------------------------------------------------------------


def _raw_cell_color(cell: Any) -> tuple[str | None, str | None]:
    """Extrai (tipo, valor) crus da cor de fundo, sem resolver tema.

    - rgb   → ("rgb", "FF4BACC6")   (hex ARGB literal)
    - theme → ("theme", "8")        (índice do tema, como string)
    - sem fill / outro → (None, None) ou (tipo, valor) literal.
    """
    if cell is None:
        return (None, None)
    fill = getattr(cell, "fill", None)
    color = getattr(fill, "start_color", None) if fill is not None else None
    if color is None:
        return (None, None)
    ctype = getattr(color, "type", None)
    if ctype == "rgb":
        val = color.value
        return ("rgb", str(val)) if val is not None else (None, None)
    if ctype == "theme":
        return ("theme", str(color.value))
    if ctype is None:
        return (None, None)
    val = getattr(color, "value", None)
    return (ctype, str(val) if val is not None else None)


def _track_color(cell: Any, palette: list[str | None], unrecognized: Counter) -> None:
    """Resolve a cor da célula e conta a ocorrência se não for reconhecida.

    "Reconhecida" = mapeia para um dono ou meio de pagamento conhecido
    (inclui branco/preto/sem-fill, que viram 'Outros'). Cores fora desses
    mapas são acumuladas para um warning agregado — nunca falham a ETL.
    """
    if cell is None:
        return
    hex_color = resolve_cell_color(cell, palette).hex
    if hex_color is None:
        return
    if hex_color in DONO_BY_HEX or hex_color in MEIO_PAGAMENTO_BY_HEX:
        return
    unrecognized[hex_color] += 1


# --------------------------------------------------------------------------
# Idempotência
# --------------------------------------------------------------------------


def _transacao_id(source_file: str, source_sheet: str, source_row: int, tipo: str) -> str:
    """sha256(source_file|source_sheet|source_row|tipo)[:16] — ver seção 6.5.

    Determinístico: rerodar a ETL sobre o mesmo XLSX produz o mesmo ID. Se a
    linha mudar de posição vira ID novo (a fonte é o XLSX, não a entidade).
    O `tipo` entra no hash porque crédito e débito dividem a mesma linha física.
    """
    raw = f"{source_file}|{source_sheet}|{source_row}|{tipo}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------
# Extração
# --------------------------------------------------------------------------


def _read_transacao(
    ws: Any,
    row: int,
    tipo: str,
    colmap: dict[str, int],
    source_file: str,
    palette: list[str | None],
    unrecognized: Counter,
    extracted_at: datetime,
) -> tuple | None:
    """Lê um lado (crédito ou débito) de uma linha; None se a linha é vazia."""
    desc_col = colmap.get("descricao")
    valor_col = colmap.get("valor")
    data_col = colmap.get("data")

    descricao = _to_str(ws.cell(row, desc_col).value) if desc_col else None
    valor = _to_decimal(ws.cell(row, valor_col).value) if valor_col else None
    data = _to_date(ws.cell(row, data_col).value) if data_col else None

    # Filtro de linha vazia (seção 6.6): descrição E valor E data nulos.
    # Linha com valor 0 é mantida (decisão fixada).
    if descricao is None and valor is None and data is None:
        return None

    cat_col = colmap.get("categoria")
    macro_col = colmap.get("macrocategoria")
    ok_col = colmap.get("status_ok")

    categoria = _to_str(ws.cell(row, cat_col).value) if cat_col else None
    macrocategoria = _to_str(ws.cell(row, macro_col).value) if macro_col else None
    status_ok = _to_str(ws.cell(row, ok_col).value) if ok_col else None

    desc_cell = ws.cell(row, desc_col) if desc_col else None
    valor_cell = ws.cell(row, valor_col) if valor_col else None
    cor_desc_tipo, cor_desc_valor = _raw_cell_color(desc_cell)
    cor_valor_tipo, cor_valor_valor = _raw_cell_color(valor_cell)
    _track_color(desc_cell, palette, unrecognized)
    _track_color(valor_cell, palette, unrecognized)

    return (
        _transacao_id(source_file, ws.title, row, tipo),
        source_file,
        ws.title,
        row,
        extracted_at,
        tipo,
        descricao,
        categoria,
        macrocategoria,
        valor,
        data,
        status_ok,
        cor_desc_tipo,
        cor_desc_valor,
        cor_valor_tipo,
        cor_valor_valor,
    )


def extract_transacoes(
    ws: Any,
    source_file: str,
    palette: list[str | None],
    unrecognized: Counter,
    extracted_at: datetime,
) -> list[tuple]:
    """Extrai transações (crédito + débito) de uma aba mensal."""
    layout = detect_month_layout(ws)
    if layout is None:
        log.warning("  aba %r: header de transações não detectado, pulando", ws.title)
        return []

    rows: list[tuple] = []
    for row in range(layout.header_row + 1, ws.max_row + 1):
        for tipo, colmap in (("credito", layout.credit), ("debito", layout.debit)):
            if not colmap or "descricao" not in colmap:
                continue
            rec = _read_transacao(
                ws, row, tipo, colmap, source_file, palette, unrecognized, extracted_at
            )
            if rec is not None:
                rows.append(rec)
    return rows


def extract_snapshots(ws: Any, source_file: str, extracted_at: datetime) -> list[tuple]:
    """Extrai todos os snapshots de carteira da aba "Situação Atual"."""
    rows: list[tuple] = []
    for block in find_snapshot_blocks(ws):
        for rec in iter_snapshot_rows(ws, block):
            rows.append(
                (
                    source_file,
                    block.marker_row,
                    extracted_at,
                    block.data_referencia,
                    _to_str(rec.get("banco_corretora")),
                    _to_str(rec.get("aplicacao")),
                    _to_decimal(rec.get("valor_bruto")),
                    _to_decimal(rec.get("alocacao_pct")),
                    _to_date(rec.get("vencimento")),
                    _to_decimal(rec.get("mom")),
                    _to_decimal(rec.get("yoy")),
                    _to_decimal(rec.get("valor_liquido_final")),
                    _to_decimal(rec.get("rendimento_atual")),
                    _to_decimal(rec.get("rendimento_final")),
                )
            )
    return rows


def extract_categorias(ws: Any) -> list[tuple]:
    """Extrai a config de categorias da aba "Configurações" (ver seção 5)."""
    rows: list[tuple] = []
    for r in range(_CONFIG_ROW_START, _CONFIG_ROW_END + 1):
        receita = _to_str(ws.cell(r, _CONFIG_COL_RECEITA).value)
        despesa = _to_str(ws.cell(r, _CONFIG_COL_DESPESA).value)
        macro = _to_str(ws.cell(r, _CONFIG_COL_MACRO).value)

        if receita and receita != _CONFIG_PLACEHOLDER:
            rows.append(("receita", receita, None))
        if despesa and despesa != _CONFIG_PLACEHOLDER:
            macro_val = macro if (macro and macro != _CONFIG_PLACEHOLDER) else None
            rows.append(("despesa", despesa, macro_val))
    return rows


# --------------------------------------------------------------------------
# DuckDB: schema + carga idempotente
# --------------------------------------------------------------------------

_DDL = """
CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE IF NOT EXISTS raw.transacoes (
    transacao_id        VARCHAR,
    source_file         VARCHAR,
    source_sheet        VARCHAR,
    source_row          INTEGER,
    extracted_at        TIMESTAMP,
    tipo_raw            VARCHAR,
    descricao_raw       VARCHAR,
    categoria_raw       VARCHAR,
    macrocategoria_raw  VARCHAR,
    valor_raw           DECIMAL(12, 2),
    data_raw            DATE,
    status_ok_raw       VARCHAR,
    cor_descricao_tipo  VARCHAR,
    cor_descricao_valor VARCHAR,
    cor_valor_tipo      VARCHAR,
    cor_valor_valor     VARCHAR
);

CREATE TABLE IF NOT EXISTS raw.carteira_snapshots (
    source_file            VARCHAR,
    source_block_start_row INTEGER,
    extracted_at           TIMESTAMP,
    data_referencia        DATE,
    banco_corretora        VARCHAR,
    aplicacao              VARCHAR,
    valor_bruto            DECIMAL(12, 2),
    alocacao_pct           DECIMAL(8, 6),
    vencimento             DATE,
    mom                    DECIMAL(10, 6),
    yoy                    DECIMAL(10, 6),
    valor_liquido_final    DECIMAL(12, 2),
    rendimento_atual       DECIMAL(18, 6),
    rendimento_final       DECIMAL(18, 6)
);

CREATE TABLE IF NOT EXISTS raw.categorias_config (
    tipo           VARCHAR,
    categoria      VARCHAR,
    macrocategoria VARCHAR
);
"""

_INSERT_TRANSACOES = "INSERT INTO raw.transacoes VALUES (" + ",".join(["?"] * 16) + ")"
_INSERT_SNAPSHOTS = "INSERT INTO raw.carteira_snapshots VALUES (" + ",".join(["?"] * 14) + ")"
_INSERT_CATEGORIAS = "INSERT INTO raw.categorias_config VALUES (?, ?, ?)"


def _create_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(_DDL)


def _reload_transacoes(con: duckdb.DuckDBPyConnection, source_file: str, rows: list[tuple]) -> None:
    con.execute("DELETE FROM raw.transacoes WHERE source_file = ?", [source_file])
    if rows:
        con.executemany(_INSERT_TRANSACOES, rows)


def _reload_snapshots(con: duckdb.DuckDBPyConnection, source_file: str, rows: list[tuple]) -> None:
    con.execute("DELETE FROM raw.carteira_snapshots WHERE source_file = ?", [source_file])
    if rows:
        con.executemany(_INSERT_SNAPSHOTS, rows)


def _reload_categorias(con: duckdb.DuckDBPyConnection, rows: list[tuple]) -> None:
    con.execute("DELETE FROM raw.categorias_config")
    if rows:
        con.executemany(_INSERT_CATEGORIAS, rows)


# --------------------------------------------------------------------------
# Orquestração
# --------------------------------------------------------------------------


def process_file(
    con: duckdb.DuckDBPyConnection,
    path: Path,
    extracted_at: datetime,
    unrecognized: Counter,
) -> None:
    """Processa um único XLSX, recarregando suas tabelas raw."""
    source_file = path.name
    log.info("Processando %s", source_file)

    palette = load_theme_palette(path)
    wb = load_workbook(path, data_only=True)
    year = _parse_year(source_file)

    transacoes: list[tuple] = []
    snapshots: list[tuple] = []
    categorias: list[tuple] = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        if _is_month_sheet(sheet_name):
            transacoes.extend(
                extract_transacoes(ws, source_file, palette, unrecognized, extracted_at)
            )
        elif _is_situacao_atual(sheet_name):
            snapshots.extend(extract_snapshots(ws, source_file, extracted_at))
        elif _is_configuracoes(sheet_name) and year == CONFIG_SOURCE_YEAR:
            categorias.extend(extract_categorias(ws))

    _reload_transacoes(con, source_file, transacoes)
    _reload_snapshots(con, source_file, snapshots)
    if categorias:
        _reload_categorias(con, categorias)

    log.info(
        "  %d transações, %d snapshots, %d categorias",
        len(transacoes),
        len(snapshots),
        len(categorias),
    )


def run(xlsx_dir: str | Path, db_path: str | Path) -> None:
    """Roda a ETL completa sobre todos os XLSX de `xlsx_dir`."""
    xlsx_dir = Path(xlsx_dir)
    db_path = Path(db_path)

    files = sorted(p for p in xlsx_dir.glob("*.xlsx") if not p.name.startswith("~$"))
    if not files:
        log.warning("Nenhum XLSX encontrado em %s", xlsx_dir)
        return

    db_path.parent.mkdir(parents=True, exist_ok=True)
    extracted_at = datetime.now()
    unrecognized: Counter = Counter()

    con = duckdb.connect(str(db_path))
    try:
        _create_schema(con)
        for path in files:
            process_file(con, path, extracted_at, unrecognized)
    finally:
        con.close()

    if unrecognized:
        log.warning(
            "Cores não reconhecidas (hex → contagem): %s",
            dict(unrecognized.most_common()),
        )
    else:
        log.info("Todas as cores foram reconhecidas.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m ingestion.extract_sheets",
        description="Extrai os XLSX de origem para a camada raw.* do DuckDB.",
    )
    parser.add_argument(
        "--xlsx-dir",
        type=Path,
        default=DEFAULT_XLSX_DIR,
        help="Diretório com os arquivos .xlsx (default: data/raw).",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help="Caminho do arquivo DuckDB (default: data/warehouse.duckdb).",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    run(args.xlsx_dir, args.db)


if __name__ == "__main__":
    main()
