---
title: Household finances
---

Six years of a couple's monthly budget workbooks, modeled with dbt into a star schema. Every number here comes from the **synthetic dataset** the repository generates, never from real finances.

Months count once they are closed: the month still being paid is left out of the totals, because its income and bills are only partly settled.

```sql last_12_months
with ranked as (
    select
        *,
        row_number() over (order by budget_month desc) as month_rank
    from warehouse.monthly_cashflow
)
select
    sum(income) filter (where month_rank <= 12) as income,
    sum(spending) filter (where month_rank <= 12) as spending,
    sum(savings) filter (where month_rank <= 12)
        / sum(income) filter (where month_rank <= 12) as savings_rate,
    sum(income) filter (where month_rank between 13 and 24) as prior_income,
    sum(spending) filter (where month_rank between 13 and 24) as prior_spending,
    sum(savings) filter (where month_rank between 13 and 24)
        / sum(income) filter (where month_rank between 13 and 24) as prior_savings_rate,
    strftime(max(budget_month) filter (where month_rank = 1), '%b %Y') as through_month
from ranked
```

```sql kpis
select
    income,
    spending,
    savings_rate,
    income / prior_income - 1 as income_change,
    spending / prior_spending - 1 as spending_change,
    (savings_rate - prior_savings_rate) * 100 as savings_rate_change_pts
from ${last_12_months}
```

```sql net_worth
select
    reference_date,
    -- noon UTC keeps the sparkline's dates on the right day in every time zone
    reference_date + interval 12 hours as snapshot_at,
    sum(gross_value) as net_worth
from warehouse.portfolio
group by reference_date
-- BigValue shows the first row, so the newest snapshot goes first
order by reference_date desc
```

```sql owed
select sum(outstanding_amount) as owed
from warehouse.installments
```

## Last 12 closed months, through <Value data={last_12_months} column=through_month />

<BigValue
    data={kpis}
    value=income
    title="Income"
    fmt=brl1k
    comparison=income_change
    comparisonFmt=pct1
    comparisonTitle="vs prior 12 months"
/>
<BigValue
    data={kpis}
    value=spending
    title="Spending"
    fmt=brl1k
    comparison=spending_change
    comparisonFmt=pct1
    comparisonTitle="vs prior 12 months"
    downIsGood=true
/>
<BigValue
    data={kpis}
    value=savings_rate
    title="Savings rate"
    fmt=pct1
    comparison=savings_rate_change_pts
    comparisonFmt=num1
    comparisonTitle="pts vs prior 12 months"
/>
<BigValue
    data={net_worth}
    value=net_worth
    title="Portfolio, latest snapshot"
    fmt=brl1k
    sparkline=snapshot_at
    sparklineType=area
/>
<BigValue
    data={owed}
    value=owed
    title="Still owed in installments"
    fmt=brl
    link="/installments"
/>

## Income and spending by month

```sql monthly_long
-- Months are drawn mid-month: a date at midnight UTC shows up as the previous
-- day (and month) in browsers west of UTC, mid-month can't cross a month.
select budget_month + interval 14 days as month, 'Income' as measure, income as amount
from warehouse.monthly_cashflow
union all
select budget_month + interval 14 days as month, 'Spending' as measure, spending as amount
from warehouse.monthly_cashflow
order by month, measure
```

<LineChart
    data={monthly_long}
    x=month
    y=amount
    series=measure
    seriesOrder={['Income', 'Spending']}
    yFmt=brl0k
    xFmt="mmm yyyy"
/>

The income peaks are profit sharing (January and July), the 13th salary (November and December) and vacation pay. Spending moves less, because fixed costs make up most of it (see [Spending](/spending)).

## By year

```sql yearly
select
    budget_year as year,
    count(*) as closed_months,
    sum(income) as income,
    sum(spending) as spending,
    sum(invested) as invested,
    sum(savings) as savings,
    sum(savings) / sum(income) as savings_rate
from warehouse.monthly_cashflow
group by budget_year
order by budget_year
```

<BarChart
    data={yearly}
    x=year
    y=savings_rate
    yFmt=pct0
    title="Savings rate"
    sort=false
    labels=true
    labelFmt=pct0
/>

<DataTable data={yearly}>
    <Column id=year />
    <Column id=closed_months title="Closed months" />
    <Column id=income fmt=brl0 />
    <Column id=spending fmt=brl0 />
    <Column id=invested fmt=brl0 title="Into investments" />
    <Column id=savings fmt=brl0 />
    <Column id=savings_rate fmt=pct1 title="Savings rate" />
</DataTable>

Savings is income minus spending: the part moved into investments plus what stayed in the account.
