"""Shared test fixtures."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ingestion.extract_sheets import run
from synthetic.generate import FILE_TEMPLATE, LAST_YEAR, generate

# Integration tests run on the synthetic workbooks, generated once per
# session. To run them against a real XLSX, point FIXTURE_XLSX at it.
FIXTURE_XLSX_ENV = "FIXTURE_XLSX"


@pytest.fixture(scope="session")
def synthetic_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Directory with the synthetic workbooks for every year (default seed and as-of)."""
    out = tmp_path_factory.mktemp("synthetic")
    generate(out)
    return out


@pytest.fixture(scope="session")
def fixture_xlsx_path(synthetic_dir: Path) -> Path:
    """XLSX for the integration tests: the newest synthetic one, or a real one."""
    override = os.environ.get(FIXTURE_XLSX_ENV)
    if override:
        path = Path(override)
        if not path.exists():
            pytest.skip(f"{FIXTURE_XLSX_ENV} points to a missing file: {path}")
        return path
    return synthetic_dir / FILE_TEMPLATE.format(year=LAST_YEAR)


@pytest.fixture(scope="session")
def raw_db(synthetic_dir: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """DuckDB with the raw.* layer loaded from the synthetic workbooks."""
    db = tmp_path_factory.mktemp("warehouse") / "warehouse.duckdb"
    run(synthetic_dir, db)
    return db
