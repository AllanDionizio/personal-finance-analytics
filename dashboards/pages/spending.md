---
title: Spending
sidebar_position: 3
---

Where the money goes. Spending counts settled debits in closed months. Money moved into investments is not spending, so it is left out (it shows up as savings on the [overview](/)).

```sql ttm_window
select
    max(budget_month) as last_month,
    strftime(max(budget_month), '%b %Y') as through_month
from warehouse.monthly_cashflow
```

```sql spending_kpis
with ranked as (
    select
        *,
        row_number() over (order by budget_month desc) as month_rank
    from warehouse.monthly_cashflow
),
totals as (
    select
        sum(spending) filter (where month_rank <= 12) as spending,
        sum(spending) filter (where month_rank between 13 and 24) as prior_spending,
        sum(fixed_spending) filter (where month_rank <= 12) as fixed_spending
    from ranked
)
select
    totals.*,
    totals.spending / totals.prior_spending - 1 as spending_growth,
    (totals.spending / totals.prior_spending) / (1 + ipca.ipca_12m) - 1 as real_spending_growth,
    ipca.ipca_12m,
    totals.fixed_spending / totals.spending as fixed_share,
    w.through_month
from totals
cross join ${ttm_window} as w
left join warehouse.inflation as ipca on ipca.month = w.last_month
```

## Last 12 closed months, through <Value data={spending_kpis} column=through_month />

<BigValue
    data={spending_kpis}
    value=spending
    title="Spending"
    fmt=brl1k
    comparison=spending_growth
    comparisonFmt=pct1
    comparisonTitle="vs prior 12 months"
    downIsGood=true
/>
<BigValue
    data={spending_kpis}
    value=real_spending_growth
    title="Real spending growth"
    fmt=pct1
/>
<BigValue
    data={spending_kpis}
    value=fixed_share
    title="Fixed share of spending"
    fmt=pct1
/>

<!-- fmt() instead of <Value>: Value leaves a space before the punctuation that follows it -->
Spending {spending_kpis[0]?.spending_growth >= 0 ? 'grew' : 'fell'} {fmt(Math.abs(spending_kpis[0]?.spending_growth), 'pct1')} against {fmt(spending_kpis[0]?.ipca_12m, 'pct1')} of inflation: in real terms, the household spent {fmt(Math.abs(spending_kpis[0]?.real_spending_growth), 'pct1')} {spending_kpis[0]?.real_spending_growth >= 0 ? 'more' : 'less'} than a year before.

## What changed in the last 12 months

```sql movers
-- The ten categories whose spending moved the most, last 12 closed months
-- against the 12 before
with w as (select * from ${ttm_window}),
by_category as (
    select
        t.category,
        sum(t.effective_amount) filter (
            where t.budget_month > w.last_month - interval 12 months
        ) as current_12m,
        sum(t.effective_amount) filter (
            where t.budget_month <= w.last_month - interval 12 months
            and t.budget_month > w.last_month - interval 24 months
        ) as prior_12m
    from warehouse.transactions as t
    cross join w
    where t.side = 'debit'
        and t.effective_amount <> 0
        and t.budget_month <= w.last_month
    group by t.category
)
select
    category,
    coalesce(current_12m, 0) as current_12m,
    coalesce(prior_12m, 0) as prior_12m,
    coalesce(current_12m, 0) - coalesce(prior_12m, 0) as change,
    case when coalesce(current_12m, 0) >= coalesce(prior_12m, 0) then 'Up' else 'Down' end as direction
from by_category
order by abs(coalesce(current_12m, 0) - coalesce(prior_12m, 0)) desc
limit 10
```

<BarChart
    data={movers}
    x=category
    y=change
    series=direction
    seriesColors={{'Up': '#e34948', 'Down': '#2a78d6'}}
    swapXY=true
    leftPadding=24
    sort=false
    yFmt=brl0
    title="Change in spending by category, vs the prior 12 months"
/>

<DataTable data={movers}>
    <Column id=category />
    <Column id=prior_12m fmt=brl0 title="Prior 12 months" />
    <Column id=current_12m fmt=brl0 title="Last 12 months" />
    <Column id=change fmt=brl0 contentType=delta downIsGood=true />
</DataTable>

## Is spending outpacing income and inflation?

```sql pace
-- Rolling 12-month income and spending, and the average price level over the
-- same 12 months, each indexed to 100 at the first full 12-month window
with rolling as (
    select
        m.budget_month,
        sum(m.income) over last_12 as income_12m,
        sum(m.spending) over last_12 as spending_12m,
        avg(i.price_index) over last_12 as price_12m,
        count(i.price_index) over last_12 as months
    from warehouse.monthly_cashflow as m
    left join warehouse.inflation as i on i.month = m.budget_month
    window last_12 as (order by m.budget_month rows between 11 preceding and current row)
),
complete as (
    select * from rolling where months = 12
),
base as (
    select * from complete order by budget_month limit 1
)
-- drawn mid-month so no browser time zone pushes a point into the month before
select c.budget_month + interval 14 days as month, 'Income' as measure,
    100 * c.income_12m / b.income_12m as index
from complete as c cross join base as b
union all
select c.budget_month + interval 14 days, 'Spending', 100 * c.spending_12m / b.spending_12m
from complete as c cross join base as b
union all
select c.budget_month + interval 14 days, 'Inflation (IPCA)', 100 * c.price_12m / b.price_12m
from complete as c cross join base as b
order by month, measure
```

<LineChart
    data={pace}
    x=month
    y=index
    series=measure
    seriesOrder={['Income', 'Spending', 'Inflation (IPCA)']}
    yFmt=num0
    xFmt="mmm yyyy"
    title="Rolling 12 months, indexed to 100 at the first full window"
/>

When the spending line climbs faster than inflation, the household is buying more, not just paying higher prices. When it climbs faster than income, the savings rate shrinks.

## Fixed and variable costs

```sql fixed_variable
-- Months are drawn mid-month: a date at midnight UTC shows up as the previous
-- day (and month) in browsers west of UTC, mid-month can't cross a month.
select budget_month + interval 14 days as month, 'Fixed' as macro_category, fixed_spending as amount
from warehouse.monthly_cashflow
union all
select budget_month + interval 14 days as month, 'Variable' as macro_category, variable_spending as amount
from warehouse.monthly_cashflow
union all
-- categories with no macro-category; only shown in months that have any
select budget_month + interval 14 days as month, 'Unclassified' as macro_category, unclassified_spending as amount
from warehouse.monthly_cashflow
where unclassified_spending <> 0
order by month, macro_category
```

<BarChart
    data={fixed_variable}
    x=month
    y=amount
    series=macro_category
    seriesOrder={['Fixed', 'Variable', 'Unclassified']}
    type=stacked
    yFmt=brl0k
    xFmt="mmm yyyy"
/>

```sql fixed_share
select
    budget_year as year,
    sum(fixed_spending) as fixed_spending,
    sum(variable_spending) as variable_spending,
    sum(fixed_spending) / sum(spending) as fixed_share
from warehouse.monthly_cashflow
group by budget_year
order by budget_year
```

<DataTable data={fixed_share}>
    <Column id=year />
    <Column id=fixed_spending fmt=brl0 title="Fixed" />
    <Column id=variable_spending fmt=brl0 title="Variable" />
    <Column id=fixed_share fmt=pct1 title="Fixed share" />
</DataTable>

## By category

```sql years
select distinct budget_year as year
from warehouse.monthly_cashflow
order by year desc
```

<Dropdown
    data={years}
    name=year
    value=year
    title="Year"
/>

```sql spending_rows
-- Debits in closed months only, the same cut monthly_cashflow makes.
select t.*
from warehouse.transactions as t
where t.side = 'debit'
    and t.effective_amount <> 0
    and t.budget_month <= (select max(budget_month) from warehouse.monthly_cashflow)
    and strftime(t.budget_month, '%Y') = '${inputs.year.value}'
```

```sql by_category
select
    category,
    macro_category,
    sum(effective_amount) as amount,
    count(*) as transactions
from ${spending_rows}
group by category, macro_category
order by amount desc
```

```sql top_categories
select category, amount
from ${by_category}
order by amount desc
limit 10
```

<BarChart
    data={top_categories}
    x=category
    y=amount
    swapXY=true
    leftPadding=24
    yFmt=brl0k
    title="Top 10 categories in {inputs.year.value}"
    sort=false
    emptySet=pass
/>

```sql by_card
select
    payment_method,
    sum(effective_amount) as amount,
    sum(effective_amount) / sum(sum(effective_amount)) over () as share
from ${spending_rows}
group by payment_method
order by amount desc
```

<DataTable data={by_category} rows=all emptySet=pass>
    <Column id=category />
    <Column id=macro_category title="Type" />
    <Column id=amount fmt=brl0 contentType=bar />
    <Column id=transactions />
</DataTable>

### By payment method

The card is read from the cell color of each debit. "Other" is any debit whose cell has no card color.

<DataTable data={by_card} emptySet=pass>
    <Column id=payment_method title="Payment method" />
    <Column id=amount fmt=brl0 />
    <Column id=share fmt=pct1 />
</DataTable>
