# 3. Define the metrics in dbt, not in the dashboard

**Status:** Accepted

## Context

Five dashboard pages show income, spending, savings and the portfolio's return. Each metric carries rules that are easy to get subtly wrong: the month still being paid must not count, money from selling an asset is cash in but not income, investment contributions are not spending. Evidence pages are SQL and Markdown, so each page could compute these numbers its own way, and two pages could disagree without any test noticing.

## Decision

Each metric is defined once, in a dbt mart, at the grain the pages read:

- [`fct_monthly_cashflow`](../../dbt/models/marts/fct_monthly_cashflow.sql): income, dividends, one-off income, fixed and variable spending, investments and savings, one row per closed month;
- [`fct_net_worth`](../../dbt/models/marts/fct_net_worth.sql): portfolio value, flows, return and inflation over the same periods, and the liquid reserve;
- [`fct_inflation_monthly`](../../dbt/models/marts/fct_inflation_monthly.sql): the IPCA series and its rates.

Evidence's source queries ([`dashboards/sources/warehouse/`](../../dashboards/sources/warehouse/)) only select from the marts, join dimension labels and sort. The pages can add the monthly values up over a window or a category, but they do not decide what counts as income, spending or a closed month.

The rules are pinned by dbt unit tests (for example, `test_monthly_cashflow_counts_closed_months_only`) and by reconciliation tests such as [`assert_cashflow_reconciles_to_transactions`](../../dbt/tests/assert_cashflow_reconciles_to_transactions.sql).

## Alternatives considered

- **Compute the metrics in the dashboard.** Fastest to change, but every page would repeat the rules, and nothing in CI would check them.
- **A semantic layer (dbt's MetricFlow) from the start.** It would also define the rollups, such as a 12-month savings rate, once. It adds a layer to learn and run before the marts and their tests existed; it is on the roadmap for the metrics that need it.

## Consequences

- Income, spending and savings have one tested, documented definition, and any tool reading the warehouse adds them up the same way the dashboard does.
- A new metric, or a change to one, is a dbt change with a test, not only a dashboard edit.
- Rollups still live in the pages. The 12-month savings rate, for one, is computed on two pages (`index.md` and `income.md`), and no test checks that they agree. Moving these ratios into the semantic layer is the next step for them.
