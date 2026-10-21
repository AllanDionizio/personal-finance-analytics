{% docs __overview__ %}
# personal-finance-analytics

Six years of household finance workbooks (Google Sheets exported to XLSX),
modeled into a star schema. The repo runs on a synthetic dataset with the
same layout as the real workbooks.

- **raw**: literal extract by the Python ingestion, provenance kept.
- **staging**: typed and cleaned; cell colors resolved to owner and payment
  method; installment tags parsed.
- **intermediate**: installment purchases rebuilt from their rows.
- **marts**: facts and dimensions for the dashboard.

Design notes and every transformation rule: `docs/data-model.md` in the
repository.
{% enddocs %}

<!-- Provenance -->

{% docs source_file %}
Workbook the row was read from, e.g. `Planilha_de_Gastos_Financeiros 2026.xlsx`.
{% enddocs %}

{% docs source_sheet %}
Month sheet the row was read from (`JAN`, `FEV`, ...).
{% enddocs %}

{% docs source_row %}
Row number in the sheet.
{% enddocs %}

{% docs source_block_row %}
Sheet row of the snapshot block's `Data Referência:` marker.
{% enddocs %}

{% docs extracted_at %}
When the ingestion read the workbook.
{% enddocs %}

<!-- Transactions -->

{% docs transaction_id %}
Deterministic id of a transaction: `sha256(source_file|source_sheet|source_row|side)[:16]`.
{% enddocs %}

{% docs transaction_date %}
Date typed on the row: the purchase date for card purchases (the same on
every installment), the payment date for bills.
{% enddocs %}

{% docs budget_month %}
First day of the month the row is budgeted in: the sheet's month in the
file's year (`JAN` in the 2026 file → 2026-01-01).
{% enddocs %}

{% docs side %}
`'credit'` (money in) or `'debit'` (money out).
{% enddocs %}

{% docs description %}
Description trimmed, whitespace collapsed, without the `(N/M)` installment tag.
{% enddocs %}

{% docs raw__description %}
Description as typed, `(N/M)` installment tag included.
{% enddocs %}

{% docs category %}
Category as typed in Portuguese, trimmed (e.g. `'Mercado'`).
{% enddocs %}

{% docs raw__category %}
Category as typed.
{% enddocs %}

{% docs raw__macro_category %}
Macro-category as typed (`'Fixo'`, `'Variável'`, `'n/a'`). The column only
exists on the debit side from 2022 on, so it is NULL in 2021 and on credits.
{% enddocs %}

{% docs category_type %}
`'income'` for credit categories, `'expense'` for debit categories.
{% enddocs %}

{% docs category_key %}
Surrogate key of (category_type, category); `'unknown'` in the facts when the
category is in no list.
{% enddocs %}

{% docs amount %}
Amount as typed. Credits are never negative. A negative debit is a refund or
discount (an estorno, a discount for paying installments early), and so is a
card adjustment (a discount on the card bill).
{% enddocs %}

{% docs payment_method %}
`'Card A'`, `'Card B'`, `'Card C'` or `'Other'`, from the debit's cell colors.
{% enddocs %}

{% docs color_type %}
How the cell's fill color is stored: `'rgb'` (a literal) or `'theme'` (an
index into the workbook's theme).
{% enddocs %}

{% docs color_value %}
The fill color as stored: an ARGB hex such as `FF4BACC6` for `rgb`, a theme
index such as `8` for `theme`.
{% enddocs %}

<!-- Flags -->

{% docs is_settled %}
True when the row's OK column says `'Sim'` (paid or received).
{% enddocs %}

{% docs is_effective %}
Settled and not an investment contribution: the row counts as real cash in
or out.
{% enddocs %}

{% docs is_dividend %}
Credit in `'Proventos'`: real-estate fund dividends.
{% enddocs %}

{% docs is_investment_contribution %}
Debit in `'Investimento'`: money moved into investments, not spent.
{% enddocs %}

{% docs is_card_adjustment %}
Debit in `'Cartão de Crédito'`: an early-payment discount or points
cashback, not a purchase.
{% enddocs %}

{% docs is_installment %}
True when the purchase is split in more than one installment.
{% enddocs %}

{% docs installment_number %}
Which installment the row is: 7 in `(7/12)`, else 1.
{% enddocs %}

{% docs installment_count %}
How many installments the purchase has: 12 in `(7/12)`, else 1.
{% enddocs %}

<!-- Installment purchases -->

{% docs purchase_id %}
Surrogate key of an installment purchase: hash of description, category,
payment method, installment count, amount and the first installment's month.
{% enddocs %}

{% docs installment_id %}
Surrogate key of (purchase_id, installment_number).
{% enddocs %}

{% docs first_recorded_installment %}
Lowest installment number the workbooks hold for the purchase.
{% enddocs %}

{% docs last_recorded_installment %}
Highest installment number the workbooks hold for the purchase.
{% enddocs %}

<!-- Portfolio -->

{% docs snapshot_id %}
Surrogate key of (reference_date, bank, asset, maturity_date): two lots
of the same product differ only by their maturity date.
{% enddocs %}

{% docs reference_date %}
Date of the portfolio snapshot (`Data Referência`).
{% enddocs %}

{% docs bank %}
Institution holding the asset, normalized to its most frequent spelling.
{% enddocs %}

{% docs raw__bank %}
Institution holding the asset, as typed.
{% enddocs %}

{% docs asset %}
Asset name, trimmed, with notes typed over a name mapped back (seed `asset_aliases`).
{% enddocs %}

{% docs raw__asset %}
Asset name as typed.
{% enddocs %}

{% docs asset_class %}
Inferred from the asset name: `'Real estate fund'`, `'Fixed income'`,
`'Multimarket fund'`, `'Crypto'`, `'Cash'` or `'Other'`.
{% enddocs %}

{% docs gross_value %}
Value of the holding on the reference date, in BRL.
{% enddocs %}

{% docs allocation_pct %}
Share of the snapshot's total, from 0 to 1. NULL in snapshots that didn't
report it.
{% enddocs %}

{% docs maturity_date %}
Maturity date of the asset; NULL when it has none (`'N/A'` in the sheet).
{% enddocs %}

{% docs mom %}
Month-over-month change of the holding's value, as a fraction.
{% enddocs %}

{% docs yoy %}
Year-over-year change of the holding's value, as a fraction.
{% enddocs %}

{% docs net_value_at_maturity %}
Projected value at maturity, net of income tax, as computed in the sheet.
{% enddocs %}

{% docs return_to_date %}
Return so far, as computed in the sheet.
{% enddocs %}

{% docs return_at_maturity %}
Projected return at maturity, as computed in the sheet.
{% enddocs %}

<!-- Dimensions -->

{% docs owner_key %}
Surrogate key of the owner.
{% enddocs %}

{% docs display_name %}
Label the dashboard shows. The placeholder itself unless a local run maps it
to a real name through env var `DISPLAY_NAMES` (macro `display_name`).
{% enddocs %}

{% docs owner %}
Whose income a credit is: `'Person A'`, `'Person B'` or `'Other'`, from the
amount cell's color.
{% enddocs %}

{% docs payment_method_key %}
Surrogate key of the payment method.
{% enddocs %}

{% docs method_type %}
`'credit_card'` for the cards, `'other'` for everything else.
{% enddocs %}

{% docs source_color %}
Cell color that encodes the value in the workbooks; NULL for `'Other'`.
{% enddocs %}

{% docs is_legacy %}
True for a category that only appears in old workbooks (seed `legacy_categories`).
{% enddocs %}

{% docs theme_index %}
Position in the workbook theme's color scheme, the index a `theme` color points to.
{% enddocs %}

{% docs hex %}
6-char uppercase hex of the theme color; NULL if it can't be resolved statically.
{% enddocs %}
