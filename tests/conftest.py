"""Fixtures e configuração compartilhada de testes."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Caminho pra um XLSX real usado como fixture de integração.
# Default: data/raw/2026.xlsx (você baixa do Drive antes de rodar).
# Pode ser sobrescrito via env var FINANCAS_FIXTURE_XLSX.
_DEFAULT_FIXTURE = Path(__file__).parent.parent / "data" / "raw" / "2026.xlsx"
FIXTURE_XLSX = Path(os.environ.get("FINANCAS_FIXTURE_XLSX", _DEFAULT_FIXTURE))


@pytest.fixture(scope="session")
def fixture_xlsx_path() -> Path:
    """Caminho pro XLSX usado em testes de integração.

    Pula o teste se o arquivo não existir.
    """
    if not FIXTURE_XLSX.exists():
        pytest.skip(
            f"Fixture XLSX não encontrado em {FIXTURE_XLSX}. "
            f"Baixe um XLSX real pra `data/raw/` ou setar FINANCAS_FIXTURE_XLSX."
        )
    return FIXTURE_XLSX
