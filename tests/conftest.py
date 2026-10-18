"""Fixtures e configuração compartilhada de testes."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ingestion.extract_sheets import run
from synthetic.generate import FILE_TEMPLATE, LAST_YEAR, generate

# Por padrão os testes de integração rodam sobre os XLSX sintéticos, gerados
# uma vez por sessão. Para rodar contra um XLSX real, aponte
# FINANCAS_FIXTURE_XLSX para ele.
FIXTURE_XLSX_ENV = "FINANCAS_FIXTURE_XLSX"


@pytest.fixture(scope="session")
def synthetic_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Diretório com os XLSX sintéticos de todos os anos (seed e as-of padrão)."""
    out = tmp_path_factory.mktemp("synthetic")
    generate(out)
    return out


@pytest.fixture(scope="session")
def fixture_xlsx_path(synthetic_dir: Path) -> Path:
    """XLSX usado nos testes de integração: o sintético mais recente ou o real."""
    override = os.environ.get(FIXTURE_XLSX_ENV)
    if override:
        path = Path(override)
        if not path.exists():
            pytest.skip(f"{FIXTURE_XLSX_ENV} aponta para um arquivo inexistente: {path}")
        return path
    return synthetic_dir / FILE_TEMPLATE.format(year=LAST_YEAR)


@pytest.fixture(scope="session")
def raw_db(synthetic_dir: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """DuckDB com a camada raw.* carregada a partir dos XLSX sintéticos."""
    db = tmp_path_factory.mktemp("warehouse") / "warehouse.duckdb"
    run(synthetic_dir, db)
    return db
