# Data model

Design doc for the data layer: architecture, the raw tables the ingestion
loads, the staging, intermediate and marts models, how each source field maps into
them, and the transformation rules and decisions behind them.

**Stack:** Python (ingestion) → DuckDB (storage) → dbt (modeling) → Evidence (dashboards)

## 1. Layers

```
XLSX workbooks (one per year, exported from Google Sheets)
       │
       ▼
  raw.*           ← literal extract (Python + openpyxl)
       │
       ▼
  staging         ← cleaning, typing, installment parsing, color mapping (dbt)
       │
       ▼
  marts           ← star schema (dbt)
       │
       ▼
  Evidence        ← dashboards
```

- **Database**: DuckDB, a single file (`data/warehouse.duckdb`)
- **Transformations**: dbt with the `dbt-duckdb` adapter
- **Ingestion**: `python -m ingestion.extract_sheets`
- **Dashboards**: Evidence reading DuckDB directly

Naming: everything this project names (tables, columns, flags) is English.
Values copied from the workbooks stay as typed in the Portuguese source
(`'Sim'`, `'Mercado'`, `'Fixo'`); staging maps the ones that drive logic.

## 2. Raw layer

Literal capture of the XLSX, **no transformation**, with provenance kept.
Each file reloads with `DELETE WHERE source_file = ?` + `INSERT`, so re-runs
are idempotent.

### `raw.transactions`

One row per side (credit or debit) of each non-empty month-sheet row.

| Column | Type | Description |
|---|---|---|
| `transaction_id` | VARCHAR | `sha256(source_file\|source_sheet\|source_row\|side)[:16]`, see 6.5 |
| `source_file` | VARCHAR | e.g. `'Planilha_de_Gastos_Financeiros 2026.xlsx'` |
| `source_sheet` | VARCHAR | `'JAN'`, `'FEV'`, ... |
| `source_row` | INTEGER | row number in the sheet |
| `extracted_at` | TIMESTAMP | when the ingestion ran |
| `side` | VARCHAR | `'credit'` or `'debit'` |
| `description` | VARCHAR | raw text, `(N/M)` tag included |
| `category` | VARCHAR | raw text |
| `macro_category` | VARCHAR | NULL in 2021 files (column didn't exist) |
| `amount` | DECIMAL(12,2) | |
| `transaction_date` | DATE | original purchase date |
| `status` | VARCHAR | `'Sim'` or `'Não'` (paid / not yet) |
| `description_color_type` | VARCHAR | `'rgb'` or `'theme'` |
| `description_color_value` | VARCHAR | ARGB hex or theme index |
| `amount_color_type` | VARCHAR | same, for the amount cell |
| `amount_color_value` | VARCHAR | |

### `raw.portfolio_snapshots`

One row per holding per snapshot block of the "Situação Atual" sheet. Every
year's file repeats the whole history, so the same snapshot appears in
several files; staging deduplicates (see 6.8).

| Column | Type |
|---|---|
| `source_file`, `source_block_row`, `extracted_at` | provenance |
| `reference_date` | DATE |
| `bank` | VARCHAR |
| `asset` | VARCHAR |
| `gross_value` | DECIMAL(12,2) |
| `allocation_pct` | DECIMAL(8,6) |
| `maturity_date` | DATE (NULL for `'N/A'`) |
| `mom`, `yoy` | DECIMAL(10,6) |
| `net_value_at_maturity` | DECIMAL(12,2) |
| `return_to_date`, `return_at_maturity` | DECIMAL(18,6) |

Columns that a block doesn't have yet (they were added over time) are NULL.

### `raw.category_config`

Canonical category list: the "Configurações" sheet of the **2026** file.

| Column | Type |
|---|---|
| `category_type` | `'income'` or `'expense'` |
| `category` | VARCHAR |
| `macro_category` | `'Fixo'`, `'Variável'`, `'n/a'` (expenses only) |

### `raw.workbook_themes`

Each workbook's theme palette, so staging can resolve `theme` color
references per file (see 6.2).

| Column | Type | Description |
|---|---|---|
| `source_file`, `extracted_at` | | provenance |
| `theme_index` | INTEGER | position in the theme's color scheme |
| `hex` | VARCHAR | 6-char uppercase hex; NULL if not resolvable statically |

## 3. Staging

Views in the `staging` schema, built by `dbt/models/staging/`. Unit tests
(`_staging__unit_tests.yml`) pin the rules of section 6 on hand-made rows.

### `stg_transactions`

| Column | Type | Rule |
|---|---|---|
| `transaction_id` | VARCHAR | from raw |
| `transaction_date` | DATE | original purchase date (years back for an installment) |
| `budget_month` | DATE | first day of the sheet's month: `JAN` in the 2026 file → `2026-01-01` |
| `side` | VARCHAR | `'credit'` / `'debit'` |
| `description` | VARCHAR | trimmed, `(N/M)` tag removed |
| `raw_description` | VARCHAR | as typed |
| `category_key` | VARCHAR | FK to `stg_categories`; NULL if the category is in no list |
| `category` | VARCHAR | trimmed, as typed in Portuguese |
| `macro_category` | VARCHAR | debits: `'Fixed'` / `'Variable'` / `'Not applicable'`, from raw or `stg_categories`, else `'Unknown'` (6.4) |
| `amount` | DECIMAL(12,2) | |
| `owner` | VARCHAR | credits: `'Person A'` / `'Person B'` / `'Other'` (6.2) |
| `payment_method` | VARCHAR | debits: `'Card A'` / `'Card B'` / `'Card C'` / `'Other'` |
| `is_settled` | BOOLEAN | `status = 'Sim'` |
| `is_effective` | BOOLEAN | settled and not an investment contribution |
| `is_dividend` | BOOLEAN | credit with category `'Proventos'` |
| `is_investment_contribution` | BOOLEAN | debit with category `'Investimento'` |
| `is_card_adjustment` | BOOLEAN | category `'Cartão de Crédito'` (6.7) |
| `installment_number` | INTEGER | 7 in `(7/12)`, else 1 |
| `installment_count` | INTEGER | 12 in `(7/12)`, else 1 |
| `is_installment` | BOOLEAN | `installment_count > 1` |
| `source_file`, `source_sheet`, `source_row` | | provenance |

### `stg_portfolio_snapshots`

Deduplicated across files (6.8). `bank` is trimmed and mapped to its most
frequent spelling, since case drifts when typed by hand (`'Banco alfa
(fundos)'`). `asset_class` is inferred from the asset name: `'Real estate
fund'` (FIIs), `'Fixed income'` (CDB, LCI, CRI, CCB, Tesouro, CDI-indexed),
`'Multimarket fund'`, `'Crypto'`, `'Cash'` (account balance) or `'Other'`
(FGTS, pension, equity). `snapshot_id` is `hash(reference_date|bank|asset)`.

### `stg_categories`

`raw.category_config` plus the legacy categories that appear only in old
files (seed `legacy_categories`, e.g. `'Farmácia'`, `'Uber'`), keyed by
`category_key = hash(category_type|category)`. The macro-category is
translated: `'Fixo'` → `'Fixed'`, `'Variável'` → `'Variable'`, `'n/a'` →
`'Not applicable'`.

## 4. Intermediate and marts

### Intermediate (views in `intermediate`)

| Model | Grain | Purpose |
|---|---|---|
| `int_installment_transactions` | one row per installment debit of `stg_transactions` | tags each row with its `purchase_id` (6.9) |
| `int_installment_purchases` | one row per installment purchase | the whole plan: count, amount, first and last month, which installments the workbooks hold |

### Marts (tables in `marts`)

Foreign keys are never NULL where the dimension applies: a category in no
list points to the `'unknown'` member of `dim_category`. `owner_key` is NULL
on debits and `payment_method_key` on credits, which a test enforces.

| Model | Grain | Key columns |
|---|---|---|
| `dim_date` | one row per day, 2020-01-01 to 2030-12-31 | `date_day`, year, month, quarter, month name, weekday, is_weekend, first/last day of month |
| `dim_category` | one row per category and type | `category_key`, `category`, `macro_category`, `category_type` |
| `dim_owner` | one row per owner | `owner_key`, `owner`, `source_color` (`'#4BACC6'`) |
| `dim_payment_method` | one row per payment method | `payment_method_key`, `payment_method`, `method_type` (`'credit_card'` / `'other'`), `source_color` |
| `fct_transactions` | one row per transaction | `transaction_id`; FKs to the dims for `transaction_date`, `budget_month`, category, owner, payment method; `purchase_id` for installments; `amount`, `effective_amount` (amount if effective, else 0), `signed_effective_amount` (+ credits, − debits); the flags and installment columns of staging |
| `fct_installments` | one row per installment of every purchase | `installment_id`, `purchase_id`, `installment_number`, `budget_month`, `transaction_id` (NULL outside the workbooks), `amount`, `outstanding_amount`, `is_recorded`, `is_settled` (6.9) |
| `fct_portfolio_snapshots` | one row per asset per reference date | `snapshot_id` (`hash(reference_date\|bank\|asset)`), `reference_date`, `bank`, `asset`, `asset_class` (`'Real estate fund'` / `'Fixed income'` / `'Multimarket fund'` / `'Crypto'` / `'Cash'` / `'Other'`), `gross_value`, `allocation_pct`, `maturity_date`, `mom`, `yoy` |

## 5. Source → model mapping

### Month sheet: credit side

| Source (XLSX) | Target (`stg_transactions`) | Rule |
|---|---|---|
| Sheet (`JAN`) + file year | `budget_month` | month name → number, first day of month |
| Col B (Descrição) | `raw_description`, `description` | trim; drop `(N/M)` |
| Col C (Categoria) | `category` | check against `stg_categories` |
| Col D (Valor) | `amount` | |
| **Col D fill color** | `owner` | see 6.2 |
| Col E (Data) | `transaction_date` | |
| Col F (OK) | `is_settled` | `'Sim'` → true |
| Col G (computed) | dropped | |
| — | `side = 'credit'`, `payment_method` NULL | |

### Month sheet: debit side

Positions differ between 2021 (I–N) and 2022+ (I–O, because of
MacroCategoria). The ingestion detects the header at runtime.

| Source (XLSX) | Target (`stg_transactions`) | Rule |
|---|---|---|
| Col I (Descrição) | `description`, `installment_number`, `installment_count` | installment regex (6.1) |
| Col J (MacroCategoria, 2022+) | `macro_category` | 2021: joined from `stg_categories` |
| Col K/J (Categoria) | `category` | |
| Col L/K (Valor) | `amount` | |
| **Amount fill color, else col I** | `payment_method` | see 6.2 |
| Col M/L (Data) | `transaction_date` | |
| Col N/M (OK) | `is_settled` | |
| — | `side = 'debit'` | |

### "Situação Atual" sheet → `raw.portfolio_snapshots`

Stacked blocks, each opened by a `Data Referência:` marker. The ingestion:

1. finds every row with a `Data Referência` marker
2. for each, finds the block's header row and reads until the next marker
3. maps headers by name, not position, since columns were added over time
4. skips empty rows and total rows (`Total:` in any label column)
5. skips blocks without a table header (the first snapshot was free text)

### "Configurações" sheet → `raw.category_config`

2026 file only:

- Col I (rows 4–38) → income categories
- Col J (rows 4–38) → expense categories
- Col K (rows 4–38) → macro-category, aligned with col J

Rows holding the `'-'` placeholder are skipped.

### `xl/theme/theme1.xml` → `raw.workbook_themes`

Every file: one row per entry of the theme's color scheme, in XML order,
which is the index a `theme` color reference points to.

## 6. Transformation rules

### 6.1 Installment tag in the description

Regex `\((\d+)\s*/\s*(\d+)\)`, anywhere in the text:

- `'Telha Norte (7/10)'` → `'Telha Norte'`, 7/10
- `'Amazon (4/4) - Smart Lock'` → `'Amazon - Smart Lock'`, 4/4
- `'Mercado'` → `'Mercado'`, 1/1, not an installment

Collapse doubled whitespace, with or without a tag, and fix the `A - - B`
left by a tag between two dashes. `ingestion/installment_parser.py` and
the dbt `clean_description` macro implement the same rules.

### 6.2 Color resolution (rgb + theme)

**Quirk**: Google Sheets exports some fills as `type='rgb'` (literal hex,
e.g. `FF4BACC6`) and others as `type='theme'` (an index into the workbook
theme, e.g. `theme=9, tint=0.0`), for the same visible color. Both have to
resolve to the same value.

**Theme resolution**: the ingestion loads each workbook's
`xl/theme/theme1.xml` into `raw.workbook_themes`, and staging joins a
`theme` reference to the palette of the same `source_file`. Resolving per
file keeps the mapping right even if a workbook was made from another
template. For the template these workbooks use:

| Index | Name | Hex | Meaning |
|---|---|---|---|
| 0 | dk1 | `#000000` | neutral |
| 1 | lt1 | `#FFFFFF` | neutral |
| 2 | dk2 | `#000000` | neutral |
| 3 | lt2 | `#FFFFFF` | neutral |
| 4 | accent1 | `#4F81BD` | — |
| 5 | accent2 | `#C0504D` | — |
| 6 | accent3 | `#9BBB59` | — |
| 7 | accent4 | `#8064A2` | — |
| 8 | accent5 | `#4BACC6` | **Person A** |
| 9 | accent6 | `#F79646` | **Person B** |

The synthetic workbooks carry openpyxl's default Office theme, which differs
in the neutral slots (2 = `#1F497D`, 3 = `#EEECE1`) and adds 10 and 11
(hyperlink colors). The owner slots, 8 and 9, are the same in both.

**Mapping** (after resolving theme → hex):

| Resolved hex | Dimension | Value |
|---|---|---|
| `4BACC6` (rgb or theme=8) | owner | Person A |
| `F79646` (rgb or theme=9) | owner | Person B |
| `FFFFFF`, `000000`, no fill | owner | Other |
| `B4A7D6` | payment method | Card A |
| `8E7CC3` | payment method | Card B |
| `9FC5E8` | payment method | Card C |
| anything else | payment method | Other |

**Debit precedence**: the payment method comes from the amount cell's color
when it is a known card, else from the description cell's. A manual
highlight (e.g. yellow) on the description never becomes a card, so a
highlighted row keeps the card from its amount cell.

**2021 rule**: the 2021 file doesn't color credits by owner, so its credits
default to `'Person A'`.

Unrecognized colors (e.g. a manual yellow highlight) are counted and logged
by the ingestion, never fatal.

### 6.3 Dates

- `transaction_date`: from the cell (original purchase date)
- `budget_month`: first day of the **sheet's** month (`JAN` 2026 → `2026-01-01`)

Use `budget_month` for monthly budget analysis and `transaction_date` for
cash flow or card statement analysis. A card purchase lands on the next
month's sheet, and each installment on a later one, so the two differ often.

### 6.4 Macro-category for 2021

The column doesn't exist in 2021. Join `category` against
`stg_categories`, which covers the canonical list and the legacy names.
A category that still doesn't match gets `'Unknown'` and is flagged by a
dbt test, so a new category typed in the sheet gets noticed.

### 6.5 `transaction_id` (idempotency)

```python
transaction_id = hashlib.sha256(
    f"{source_file}|{source_sheet}|{source_row}|{side}".encode()
).hexdigest()[:16]
```

Re-running on the same XLSX gives the same id. If a row moves in the XLSX
it gets a new id, which is fine: the source of truth is the workbook, not a
logical entity. `side` is part of the hash because credit and debit share
each sheet row.

### 6.6 Empty rows

A side is empty when description, amount and date are all null; it is
skipped. A zero amount (e.g. a benefit row left at 0) is **kept**, since
"no payment this month" is information.

### 6.7 Categories with dedicated flags

| Category | Side | Flag | Meaning |
|---|---|---|---|
| `Proventos` | credit | `is_dividend` | real-estate fund dividend |
| `Investimento` | debit | `is_investment_contribution` | money moved to investments; excluded from `effective_amount` |
| `Cartão de Crédito` | debit | `is_card_adjustment` | rare: early-payment discount or points converted to cashback. **Not a purchase.** |

`effective_amount` leaves out investment contributions, so it reflects the
month's real cash impact.

### 6.8 Portfolio snapshots across files

"Situação Atual" is cumulative: the 2024 file holds every snapshot up to
2024, the 2025 file repeats them and adds 2025's, and so on. Staging keeps,
for each `reference_date`, the rows from the newest file, which also picks up
any later correction to an old block.

A note typed over an asset name (the 2026 rate change of `'180% CDI'` was
typed as `'Alterado para 110% CDI'`) maps back to the asset through the
seed `asset_aliases`, so its history stays one series. `raw_asset` keeps
the name as typed.

### 6.9 Installment purchases

Each workbook holds only the installments that fall in its year, and there
is no workbook before 2021 or after the newest year. So a purchase from late
2020 is missing its first installments, and one from late 2026 its last.

- **Purchase key**: `purchase_id = hash(description, category,
  payment_method, installment_count, amount, first_budget_month)`, where
  `first_budget_month = budget_month - (installment_number - 1) months`.
  The date is left out: a bill paid in installments (e.g. IPTU) carries
  each payment's own date. A test checks that no two rows of the key share
  an installment number.
- **Schedule**: `fct_installments` lays out installments 1 to N of each
  purchase.
- **Settled**: every installment before the as-of month (the newest month
  with a settled transaction) is paid. In the sheets a past installment is
  always paid, so a leftover `'Não'` is a typing slip, and installments
  before 2021 are in no workbook. From the as-of month on, a recorded
  installment keeps the sheet's status, and one past the newest workbook is
  outstanding. `fct_transactions` still carries the status as typed.
- **What is still owed**: `sum(outstanding_amount)`.

## 7. Decisions

1. **2021 credits have no owner color** → default to `'Person A'`
2. **Category `'Cartão de Crédito'`** → `is_card_adjustment`; it means an early-payment discount or a points cashback
3. **Portfolio history** → load every snapshot, not just the latest
4. **Canonical categories** → the 2026 file
5. **Zero-amount rows** → kept
6. **Google Sheets theme colors** → each workbook's `theme1.xml` loaded into `raw.workbook_themes` and resolved per file in staging; one mapping for rgb and theme
7. **Data entry UI** → out of scope; ingestion, modeling and dashboards come first
8. **Debit payment method** → amount cell color first, description cell color as fallback
9. **Asset renamed by a typed note** → mapped back through the seed `asset_aliases`
10. **Installments outside the workbooks** → rebuilt from the purchase plan in `fct_installments`
11. **Past installments** → always paid in `fct_installments`, whatever the sheet says

## 8. Bugs found with the synthetic data (fixed)

- **Colliding `transaction_id`**: the hash used only `(file, sheet, row)`,
  but credit and debit share each sheet row. On the synthetic data, 934 of
  4,142 transactions had a duplicate id. Fix: `side` in the hash.
- **`Total:` row loaded as a holding**: the filter only checked the block's
  first column (B), but the label sits in C. That added 137 rows to the
  portfolio snapshots and doubled any per-snapshot sum. Fix: check every
  label column and match the whole label (`Total`, `Total:`), so an asset
  like "Total Return Fund" is kept.
