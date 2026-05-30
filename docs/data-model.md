# Modelo de Dados — Controle Financeiro Pessoal

> Design doc da camada de dados. Cobre arquitetura, schema completo (DDL),
> mapeamento dos campos das planilhas atuais para o novo modelo, regras de
> transformação e decisões fixadas.
>
> **Versão:** 2 (decisões fixadas em conversa)
> **Stack:** Python (ingestão) → DuckDB (storage) → dbt (modelagem) → Evidence.dev (dashboards)

## 1. Arquitetura em camadas

```
XLSX (Google Drive)
       │
       ▼
  raw.*           ← extract literal das planilhas (Python + openpyxl)
       │
       ▼
  stg.*           ← cleaning, typing, parsing de parcela, mapeamento de cor (dbt)
       │
       ▼
  marts.*         ← modelo dimensional (dbt)
       │
       ▼
  Evidence.dev    ← dashboards
```

- **Banco**: DuckDB (arquivo único `data/financas.duckdb`)
- **Transformações**: dbt com adapter `dbt-duckdb`
- **Ingestão**: script Python (`ingestion/extract_sheets.py`)
- **Visualização**: Evidence.dev consumindo DuckDB direto

## 2. Camada Raw

Captura literal do XLSX, **sem transformação**, com proveniência preservada.

### `raw.transacoes`

| Coluna | Tipo | Descrição |
|---|---|---|
| `source_file` | VARCHAR | `'2026.xlsx'` |
| `source_sheet` | VARCHAR | `'JAN'`, `'FEV'`, ... |
| `source_row` | INTEGER | nº da linha no XLSX |
| `extracted_at` | TIMESTAMP | quando rodou a ETL |
| `tipo_raw` | VARCHAR | `'credito'` ou `'debito'` |
| `descricao_raw` | VARCHAR | texto cru com sufixo `(N/M)` |
| `categoria_raw` | VARCHAR | texto cru |
| `macrocategoria_raw` | VARCHAR | NULL para arquivos pré-2026 |
| `valor_raw` | DECIMAL(12,2) | |
| `data_raw` | DATE | data original da compra |
| `status_ok_raw` | VARCHAR | `'Sim'` ou `'Não'` |
| `cor_descricao_tipo` | VARCHAR | `'rgb'` ou `'theme'` |
| `cor_descricao_valor` | VARCHAR | hex ARGB ou índice de tema |
| `cor_valor_tipo` | VARCHAR | redundância pra validação |
| `cor_valor_valor` | VARCHAR | redundância |

### `raw.carteira_snapshots`

| Coluna | Tipo |
|---|---|
| `source_file`, `source_block_start_row`, `extracted_at` | metadados |
| `data_referencia` | DATE |
| `banco_corretora` | VARCHAR |
| `aplicacao` | VARCHAR |
| `valor_bruto` | DECIMAL(12,2) |
| `alocacao_pct` | DECIMAL(8,6) |
| `vencimento` | DATE (NULL para `'N/A'`) |
| `mom`, `yoy` | DECIMAL(10,6) |
| `valor_liquido_final`, `rendimento_atual`, `rendimento_final` | DECIMAL |

Implementação: ETL detecta blocos procurando células `'Data Referência'` e itera até a próxima ou até o fim da aba. Importar **todos os snapshots históricos** (decisão fixada).

### `raw.categorias_config`

Fonte canônica: aba "Configurações" do arquivo **2026** (decisão fixada).

| Coluna | Tipo |
|---|---|
| `tipo` | `'receita'` ou `'despesa'` |
| `categoria` | VARCHAR |
| `macrocategoria` | `'Fixo'`, `'Variável'`, `'n/a'` (só pra despesa) |

## 3. Camada Staging

### `stg.transacoes`

```sql
CREATE TABLE stg.transacoes (
    transacao_id VARCHAR PRIMARY KEY,
        -- hash(source_file || source_sheet || source_row)

    -- temporal
    data_transacao DATE,
        -- data original da compra (pode ser de anos atrás se parcela)
    data_competencia DATE,
        -- primeiro dia do mês da aba: JAN 2026 → 2026-01-01
    ano_competencia INTEGER,
    mes_competencia INTEGER,

    -- transação
    tipo VARCHAR,                       -- 'credito' | 'debito'
    descricao VARCHAR,                  -- limpa, sem sufixo de parcela
    descricao_original VARCHAR,         -- raw, com sufixo
    categoria VARCHAR,
    macrocategoria VARCHAR,             -- inferida pra <2026 via join com config
    valor DECIMAL(12,2),

    -- dimensões derivadas de cor (mapeamento normalizado rgb+theme)
    dono VARCHAR,                       -- 'Person A' | 'Person B' | 'Outros'
    meio_pagamento VARCHAR,             -- 'Card A' | 'Card B' | 'Outro'

    -- flags
    status_ok BOOLEAN,                  -- 'Sim' → true, 'Não' → false
    eh_efetivo BOOLEAN,                 -- status_ok AND categoria <> 'Investimento'
    eh_provento BOOLEAN,                -- tipo='credito' AND categoria='Proventos'
    eh_aporte_investimento BOOLEAN,     -- tipo='debito' AND categoria='Investimento'
    eh_ajuste_fatura BOOLEAN,           -- categoria='Cartão de Crédito' (raro: desconto antecipação, cashback de pontos)

    -- parcela
    parcela_num INTEGER,                -- 7
    parcela_total INTEGER,              -- 12
    eh_parcelada BOOLEAN,               -- parcela_total > 1

    -- proveniência
    source_file VARCHAR,
    source_sheet VARCHAR,
    source_row INTEGER
);
```

## 4. Camada Marts (modelo dimensional)

### `marts.dim_data`

Gerada por SQL (não vem das planilhas). Cobertura: 2020-01-01 a 2030-12-31.

```sql
CREATE TABLE marts.dim_data (
    data_key DATE PRIMARY KEY,
    ano INTEGER, mes INTEGER, dia INTEGER,
    trimestre INTEGER, semestre INTEGER,
    nome_mes VARCHAR,                   -- 'Janeiro'
    nome_dia_semana VARCHAR,
    dia_semana INTEGER,                 -- 1=segunda
    eh_fim_de_semana BOOLEAN,
    primeiro_dia_mes DATE,
    ultimo_dia_mes DATE
);
```

### `marts.dim_categoria`

```sql
CREATE TABLE marts.dim_categoria (
    categoria_key VARCHAR PRIMARY KEY,  -- 'CAT_DESP_MERCADO'
    categoria VARCHAR,                  -- 'Mercado'
    macrocategoria VARCHAR,             -- 'Fixo' | 'Variável' | 'n/a'
    tipo VARCHAR                        -- 'receita' | 'despesa'
);
```

### `marts.dim_dono`

```sql
CREATE TABLE marts.dim_dono (
    dono_key VARCHAR PRIMARY KEY,
    dono VARCHAR,                       -- 'Person A' | 'Person B' | 'Outros'
    cor_origem VARCHAR                  -- '#4BACC6'
);
```

### `marts.dim_meio_pagamento`

```sql
CREATE TABLE marts.dim_meio_pagamento (
    meio_pagamento_key VARCHAR PRIMARY KEY,
    meio_pagamento VARCHAR,             -- 'Card A' | 'Card B' | 'Outro'
    tipo VARCHAR,                       -- 'cartao_credito' | 'outro'
    cor_origem VARCHAR
);
```

### `marts.fct_transacao`

```sql
CREATE TABLE marts.fct_transacao (
    transacao_id VARCHAR PRIMARY KEY,

    -- FKs
    data_transacao_key DATE,
    data_competencia_key DATE,
    categoria_key VARCHAR,
    dono_key VARCHAR,
    meio_pagamento_key VARCHAR,

    -- atributos
    descricao VARCHAR,
    tipo VARCHAR,

    -- medidas
    valor DECIMAL(12,2),
    valor_efetivo DECIMAL(12,2),        -- valor se eh_efetivo else 0

    -- flags
    status_ok BOOLEAN,
    eh_efetivo BOOLEAN,
    eh_provento BOOLEAN,
    eh_aporte_investimento BOOLEAN,
    eh_ajuste_fatura BOOLEAN,
    eh_parcelada BOOLEAN,
    parcela_num INTEGER,
    parcela_total INTEGER
);
```

### `marts.fct_carteira_snapshot`

```sql
CREATE TABLE marts.fct_carteira_snapshot (
    snapshot_id VARCHAR PRIMARY KEY,    -- hash(data_referencia || aplicacao)
    data_referencia_key DATE,
    banco_corretora VARCHAR,
    aplicacao VARCHAR,
    classe_ativo VARCHAR,               -- inferida: 'FII' | 'RF' | 'FIM' | 'Cripto' | 'Caixa' | 'Outro'
    valor_bruto DECIMAL(12,2),
    alocacao_pct DECIMAL(8,6),
    vencimento DATE,
    mom DECIMAL(10,6),
    yoy DECIMAL(10,6)
);
```

## 5. Mapeamento XLSX → Modelo

### Aba mensal — lado CRÉDITOS

| Origem (XLSX) | Destino (stg.transacoes) | Transformação |
|---|---|---|
| Aba (`JAN`) + arquivo (`2026.xlsx`) | `ano_competencia`, `mes_competencia`, `data_competencia` | nome do mês → número; primeiro dia do mês |
| Col B (Descrição) | `descricao_original`, `descricao` | trim; remover sufixo `(N/M)` |
| Col C (Categoria) | `categoria` | validar contra `raw.categorias_config` |
| Col D (Valor) | `valor` | manter decimal |
| **Cor da col D** | `dono` | ver seção 6.2 |
| Col E (Data) | `data_transacao` | |
| Col F (OK) | `status_ok` | `'Sim'` → true |
| Col G (calculado) | descartar | |
| — | `tipo` = `'credito'`, `meio_pagamento` = NULL | |

### Aba mensal — lado DÉBITOS

Posições mudam entre 2021 (I–N) e 2022+ (I–O por causa de MacroCategoria).
ETL detecta header dinamicamente.

| Origem (XLSX) | Destino (stg.transacoes) | Transformação |
|---|---|---|
| Col I (Descrição) | `descricao`, `parcela_num`, `parcela_total` | regex de parcela (seção 6.1) |
| Col J (MacroCategoria, só 2026) | `macrocategoria` | pré-2026: inferir via join `categorias_config` |
| Col K/J (Categoria) | `categoria` | |
| Col L/K (Valor) | `valor` | |
| **Cor da col I ou da col valor** | `meio_pagamento` | ver seção 6.2 |
| Col M/L (Data) | `data_transacao` | |
| Col N/M (OK) | `status_ok` | |
| — | `tipo` = `'debito'` | |

### Aba "Situação Atual" → `raw.carteira_snapshots`

Estrutura: blocos repetidos separados por `Data Referência:`. ETL:
1. Lê toda a aba
2. Encontra todas as linhas com `'Data Referência'`
3. Para cada `Data Referência`, lê o header do bloco (linha seguinte) e itera até a próxima `Data Referência` ou fim
4. Pula linhas-resumo (`Total:` etc.)
5. Headers podem variar entre snapshots — usar nome da coluna do header do bloco, não posição fixa

### Aba "Configurações" → `raw.categorias_config`

Só do arquivo **2026.xlsx**:
- Col I (linhas 4–38) → receitas
- Col J (linhas 4–38) → despesas
- Col K (linhas 4–38) → macrocategoria (alinhada com col J)

Filtrar linhas com valor `'-'` (placeholder vazio).

## 6. Regras de transformação críticas

### 6.1 Parcela embutida na descrição

Regex `\((\d+)/(\d+)\)` global. Casos:

- `'Telha Norte (7/10)'` → descricao=`'Telha Norte'`, 7/10
- `'Amazon (4/4) - Smart Lock'` → descricao=`'Amazon - Smart Lock'`, 4/4
- `'Mercado'` → descricao=`'Mercado'`, parcela_num=1, parcela_total=1, eh_parcelada=false

Normalizar espaços duplos depois da remoção.

### 6.2 Resolução de cores (rgb + theme)

**Quirk descoberto na investigação**: o Google Sheets exporta algumas cores
como `type='rgb'` (hex direto, ex `FF4BACC6`) e outras como `type='theme'`
(referência ao tema do workbook, ex `theme=9, tint=0.0`). A ETL precisa
resolver os dois casos.

**Resolução de tema**: parsear `xl/theme/theme1.xml` do XLSX. Para o
template usado, o color scheme é:

| Index | Nome | Hex | Significado |
|---|---|---|---|
| 0 | dk1 | `#000000` | neutro |
| 1 | lt1 | `#FFFFFF` | neutro |
| 2 | dk2 | `#000000` | neutro |
| 3 | lt2 | `#FFFFFF` | neutro |
| 4 | accent1 | `#4F81BD` | — |
| 5 | accent2 | `#C0504D` | — |
| 6 | accent3 | `#9BBB59` | — |
| 7 | accent4 | `#8064A2` | — |
| 8 | accent5 | `#4BACC6` | **Person A** |
| 9 | accent6 | `#F79646` | **Person B** |

**Mapeamento final** (depois de resolver theme → hex):

| Hex resolvido | Dimensão | Valor |
|---|---|---|
| `4BACC6` (rgb direto OU theme=8) | dono | Person A |
| `F79646` (rgb direto OU theme=9) | dono | Person B |
| `FFFFFF`, `000000`, sem fill | dono | Outros |
| `B4A7D6` | meio_pagamento | Card A |
| `8E7CC3` | meio_pagamento | Card B |
| outras | meio_pagamento | Outro |

**Regra adicional pra 2021**: arquivo não usa cor pra dono. Atribuir tudo
como `'Person A'` (decisão fixada — usuário vai revisar manualmente após
ingestão).

**Pseudocódigo da resolução**:

```python
def resolve_color(cell, theme_map):
    fill = cell.fill.start_color
    if fill.type == 'rgb' and fill.value:
        return fill.value[-6:].upper()  # remove alpha
    elif fill.type == 'theme':
        idx = int(fill.value)
        return theme_map[idx].upper()
    return None
```

### 6.3 Datas

- `data_transacao`: vem da célula (data original da compra)
- `data_competencia`: primeiro dia do mês da **aba** (JAN 2026 → 2026-01-01)

Use `data_competencia` para análises mensais/orçamentárias; use
`data_transacao` para análises de fluxo de caixa real ou fatura do cartão.

### 6.4 Macrocategoria para arquivos pré-2026

Coluna não existe na origem. Joinar `categoria` contra
`raw.categorias_config` (fonte 2026). Se a categoria não existir nas
Configurações 2026, marcar como `'Desconhecido'` e logar.

### 6.5 `transacao_id` (idempotência)

```python
import hashlib
transacao_id = hashlib.sha256(
    f"{source_file}|{source_sheet}|{source_row}".encode()
).hexdigest()[:16]
```

Rodar a ETL N vezes sobre o mesmo XLSX produz o mesmo ID. Se a linha
mudar de posição no XLSX, vira ID novo — isso é OK porque a fonte é o
XLSX, não a entidade lógica.

### 6.6 Filtro de linhas

Linha "vazia": descrição E valor E data todos nulos → ignorar.
Linha com valor 0 (ex.: `Vale-Refeição` zerado): **manter** (decisão
fixada) — útil para análise de "esse mês não teve VR".

### 6.7 Categorias especiais com flags dedicadas

| Categoria | tipo | Flag | Significado |
|---|---|---|---|
| `Proventos` | crédito | `eh_provento=true` | Provento de FII pago |
| `Investimento` | débito | `eh_aporte_investimento=true` | Aporte; não conta no `valor_efetivo` |
| `Cartão de Crédito` | débito | `eh_ajuste_fatura=true` | Raro: desconto por antecipação, cashback de pontos. **Não é compra individual.** |

`valor_efetivo` exclui aportes de investimento, refletindo o impacto real no fluxo de caixa do mês.

## 7. Decisões fixadas

1. ✅ **2021 sem cor de dono** → tudo `'Person A'`, revisão manual posterior
2. ✅ **Categoria `'Cartão de Crédito'`** → flag `eh_ajuste_fatura`; semântica: desconto por antecipação OU conversão de pontos em cashback
3. ✅ **Carteira histórica** → importar TODOS os snapshots
4. ✅ **Configurações canônicas** → arquivo 2026
5. ✅ **Linhas com valor 0** → manter
6. ✅ **Theme colors do Google Sheets** → resolver via parsing do `theme1.xml`; mapeamento normalizado
7. ✅ **UI de entrada (Fase 3)** → adiada; foco em ingestão + modelagem + dashboard primeiro

## 8. Estrutura inicial do repo

```
<nome-do-repo>/
├── README.md
├── pyproject.toml              # dependências: openpyxl, duckdb, pandas
├── .gitignore                  # data/raw/, data/financas.duckdb, .env
├── data/
│   ├── raw/                    # XLSX baixados (gitignore)
│   └── financas.duckdb         # banco (gitignore)
├── ingestion/
│   ├── __init__.py
│   ├── extract_sheets.py       # main: lê XLSX → grava raw.*
│   ├── color_resolver.py       # resolve theme → hex
│   ├── parcela_parser.py       # regex de parcela
│   └── snapshot_blocks.py      # detecta blocos da Situação Atual
├── dbt_project/
│   ├── dbt_project.yml
│   ├── profiles.yml            # adapter: duckdb
│   ├── models/
│   │   ├── staging/
│   │   │   ├── stg_transacoes.sql
│   │   │   ├── stg_carteira_snapshots.sql
│   │   │   └── stg_categorias.sql
│   │   └── marts/
│   │       ├── dim_data.sql
│   │       ├── dim_categoria.sql
│   │       ├── dim_dono.sql
│   │       ├── dim_meio_pagamento.sql
│   │       ├── fct_transacao.sql
│   │       └── fct_carteira_snapshot.sql
│   └── tests/
├── dashboard/                  # Evidence.dev
│   ├── package.json
│   ├── sources/duckdb/
│   └── pages/
│       ├── index.md            # visão geral
│       ├── orcamento.md        # 30/50/10/10 + meta 20%
│       ├── categorias.md
│       ├── parcelas.md         # parcelas futuras
│       └── carteira.md         # série temporal patrimônio
└── docs/
    └── data-model.md           # este arquivo
```

## 9. Próximos passos

1. Setup do repo + `pyproject.toml`
2. `ingestion/color_resolver.py` + `parcela_parser.py` (lib testável isolada)
3. `ingestion/extract_sheets.py` (main da Fase 0)
4. Carregamento `raw.*` no DuckDB; validação manual contra totais da planilha
5. dbt staging
6. dbt marts (incluindo geração de `dim_data`)
7. Setup do Evidence.dev
8. Primeira página de dashboard (orçamento)
