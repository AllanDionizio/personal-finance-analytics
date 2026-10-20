---
title: Household finances
sidebar_position: 1
---

```sql ttm
-- Last 12 closed months against the 12 before. The month still being paid is
-- not in monthly_cashflow, so a partial month never drags the totals down.
with ranked as (
    select
        *,
        row_number() over (order by budget_month desc) as month_rank
    from warehouse.monthly_cashflow
)
select
    sum(income) filter (where month_rank <= 12) as income,
    sum(spending) filter (where month_rank <= 12) as spending,
    sum(savings) filter (where month_rank <= 12) as savings,
    sum(fixed_spending) filter (where month_rank <= 12) as fixed_spending,
    sum(income) filter (where month_rank between 13 and 24) as prior_income,
    sum(savings) filter (where month_rank between 13 and 24) as prior_savings,
    sum(fixed_spending) filter (where month_rank between 13 and 24) as prior_fixed_spending,
    strftime(max(budget_month) filter (where month_rank = 1), '%b %Y') as through_month
from ranked
```

```sql kpis
select
    *,
    savings / income as savings_rate,
    (savings / income - prior_savings / prior_income) * 100 as savings_rate_change_pts,
    fixed_spending / income as fixed_share,
    (fixed_spending / income - prior_fixed_spending / prior_income) * 100 as fixed_share_change_pts
from ${ttm}
```

```sql worth
-- Newest snapshot first: BigValue shows the first row and draws the sparkline
-- from all of them. Noon UTC keeps each date on its day in every time zone.
select
    now_.*,
    now_.reference_date + interval 12 hours as snapshot_at,
    now_.total_value / year_ago.total_value - 1 as value_change_1y
from warehouse.net_worth as now_
asof left join warehouse.net_worth as year_ago
    on now_.reference_date - interval 1 year >= year_ago.reference_date
order by now_.reference_date desc
```

```sql real_return
-- The newest snapshot whose 12-month return can be compared with inflation
select
    *,
    reference_date + interval 12 hours as snapshot_at,
    strftime(reference_date, '%b %Y') as through_month
from warehouse.net_worth
where real_return_12m is not null
order by reference_date desc
```

```sql owed
select
    sum(outstanding_amount) as owed,
    sum(outstanding_amount) / ((select income from ${ttm}) / 12) as months_of_income
from warehouse.installments
```

<!-- fmt() instead of <Value>: Value leaves a space before the punctuation that follows it -->

<div class="hero">

Over the 12 months through **{kpis[0]?.through_month}**, the household earned **{fmt(kpis[0]?.income, 'brl0')}**, spent **{fmt(kpis[0]?.spending, 'brl0')}** and kept **{fmt(kpis[0]?.savings_rate, 'pct1')}** of its income.

The portfolio is worth **{fmt(worth[0]?.total_value, 'brl0')}**, {fmt(Math.abs(worth[0]?.value_change_1y), 'pct1')} {worth[0]?.value_change_1y >= 0 ? 'more' : 'less'} than a year earlier. Over the 12 months through {real_return[0]?.through_month}, it returned {fmt(real_return[0]?.return_12m, 'pct1')} against {fmt(real_return[0]?.inflation_12m, 'pct1')} of inflation (IPCA): {#if real_return[0]?.real_return_12m >= 0}a real gain of **{fmt(real_return[0]?.real_return_12m, 'pct1')}**{:else}a real **loss** of {fmt(Math.abs(real_return[0]?.real_return_12m), 'pct1')}{/if}.

The liquid reserve covers **{fmt(worth[0]?.reserve_months, 'num1')} months** of fixed costs ({worth[0]?.reserve_status?.toLowerCase()}: 6 to 12 months). Installments still owed add up to **{fmt(owed[0]?.owed, 'brl0')}**, about {fmt(owed[0]?.months_of_income, 'num1')} months of income.

</div>

<div class="kpi-grid">

<BigValue
    data={worth}
    value=total_value
    title="Portfolio"
    fmt=brl1k
    comparison=value_change_1y
    comparisonFmt=pct1
    comparisonTitle="in a year"
    sparkline=snapshot_at
    sparklineType=area
    link="/portfolio"
/>
<BigValue
    data={kpis}
    value=savings_rate
    title="Savings rate, 12 months"
    fmt=pct1
    comparison=savings_rate_change_pts
    comparisonFmt=num1
    comparisonTitle="pts vs prior 12 months"
/>
<BigValue
    data={real_return}
    value=real_return_12m
    title="Real return, 12 months"
    fmt=pct1
    sparkline=snapshot_at
    link="/portfolio"
/>
<BigValue
    data={kpis}
    value=fixed_share
    title="Fixed costs, share of income"
    fmt=pct1
    comparison=fixed_share_change_pts
    comparisonFmt=num1
    comparisonTitle="pts vs prior 12 months"
    downIsGood=true
    link="/spending"
/>
<BigValue
    data={worth}
    value=reserve_months
    title="Liquid reserve, months of fixed costs"
    fmt=num1
    sparkline=snapshot_at
    link="/portfolio"
/>
<BigValue
    data={owed}
    value=owed
    title="Still owed in installments"
    fmt=brl0
    link="/installments"
/>

</div>

## Monthly result

```sql monthly_result
-- Months are drawn mid-month: a date at midnight UTC shows up as the previous
-- day (and month) in browsers west of UTC, mid-month can't cross a month.
select
    budget_month + interval 14 days as month,
    savings as result,
    case when savings >= 0 then 'Surplus' else 'Deficit' end as outcome
from warehouse.monthly_cashflow
order by month
```

<BarChart
    data={monthly_result}
    x=month
    y=result
    series=outcome
    seriesColors={{'Surplus': ['#5650d6', '#8a85f0'], 'Deficit': ['#e34948', '#e66767']}}
    yFmt=brl0k
    xFmt="mmm yyyy"
/>

Income minus spending, month by month. The surplus is what pays for the contributions on the [portfolio](/portfolio) page.

## The rest of the story

<div class="chapters">

- **[Income](/income)** Where the money comes from, and how much of it is salary, variable pay or dividends
- **[Spending](/spending)** Where it goes, what changed over the last year, and whether spending is outpacing income and inflation
- **[Installments](/installments)** How much of the future is already committed
- **[Portfolio](/portfolio)** Whether the portfolio grows from contributions or from returns, and whether it beats inflation

</div>

## How it's built

<!-- rel=external: the dbt docs are a separate page, not a route of this app -->
Every number here comes from a dbt mart. The <a href="/dbt-docs/" rel="external">dbt docs</a> describe each model, column and test, with the lineage from the workbooks to these pages; the code is on [GitHub](https://github.com/AllanDionizio/personal-finance-analytics).

<small>Synthetic data generated by the repository, never real finances. A month counts once it is closed.</small>
