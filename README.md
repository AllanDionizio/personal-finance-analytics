# Finanças Pessoais

Pipeline de dados para controle financeiro pessoal. Ingere planilhas
históricas (Google Sheets exportadas como XLSX), normaliza num modelo
dimensional, e gera dashboards.

## Stack

| Camada | Tecnologia |
|---|---|
| Ingestão | Python + openpyxl (preserva cor de célula como dado) |
| Storage | DuckDB (banco file-based, columnar) |
| Modelagem | dbt com adapter `dbt-duckdb` |
| Visualização | Evidence.dev |

Ver `docs/data-model.md` para o design completo da camada de dados.

## Setup

Requer Python 3.11+.

```bash
# com uv (recomendado)
uv sync --all-extras

# com pip
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Estrutura

```
financas-pessoais/
├── docs/
│   └── data-model.md            # design da camada de dados
├── ingestion/
│   ├── color_resolver.py        # cor de célula (rgb/theme) → dimensão de negócio
│   ├── parcela_parser.py        # extrai (N/M) da descrição
│   └── snapshot_blocks.py       # detecta blocos da aba "Situação Atual"
├── tests/                       # testes unitários e de integração
├── data/
│   ├── raw/                     # XLSX de origem (gitignored)
│   └── financas.duckdb          # banco gerado (gitignored)
└── pyproject.toml
```

## Uso

```bash
# Rodar testes
pytest

# Cobertura
pytest --cov=ingestion --cov-report=term-missing

# Lint
ruff check .
ruff format .

# Type check
mypy ingestion/
```

## Roadmap

- [x] Design do modelo de dados (`docs/data-model.md`)
- [x] Lib: `color_resolver` (cor → dono / meio_pagamento)
- [x] Lib: `parcela_parser` (extração de parcela embutida na descrição)
- [x] Lib: `snapshot_blocks` (parsing de blocos da Situação Atual)
- [ ] Orquestrador `extract_sheets.py` (Fase 0)
- [ ] Carregamento na camada `raw.*` do DuckDB
- [ ] Modelos dbt staging
- [ ] Modelos dbt marts (modelo dimensional)
- [ ] Dashboards Evidence
- [ ] (Opcional) UI de entrada
