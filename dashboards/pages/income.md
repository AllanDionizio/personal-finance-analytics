---
title: Income
sidebar_position: 2
---

Where the money comes from. Income here is **operating income**: what was earned, from salary to dividends. Money from selling an asset is real cash in, but it doesn't repeat, so it is kept apart (see the end of the page).

```sql closed_credits
-- Settled credits in closed months, labeled by source group
select
    t.*,
    strftime(t.budget_month, '%Y') as year
from warehouse.transactions as t
where t.side = 'credit'
    and t.effective_amount <> 0
    and t.budget_month <= (select max(budget_month) from warehouse.monthly_cashflow)
```

```sql ttm_window
select
    max(budget_month) as last_month,
    max(budget_month) - interval 11 months as first_month,
    max(budget_month) - interval 23 months as prior_first_month,
    strftime(max(budget_month), '%b %Y') as through_month
from warehouse.monthly_cashflow
```

```sql ttm_income
with w as (select * from ${ttm_window})
select
    sum(c.effective_amount) filter (
        where c.is_operating and c.budget_month >= w.first_month
    ) as income,
    sum(c.effective_amount) filter (
        where c.is_operating and c.budget_month >= w.prior_first_month and c.budget_month < w.first_month
    ) as prior_income,
    sum(c.effective_amount) filter (
        where c.income_group = 'Dividends' and c.budget_month >= w.first_month
    ) as dividends,
    any_value(w.through_month) as through_month
from ${closed_credits} as c
cross join w
```

```sql income_kpis
select
    i.*,
    i.income / i.prior_income - 1 as income_growth,
    (1 + i.income / i.prior_income - 1) / (1 + ipca.ipca_12m) - 1 as real_income_growth,
    ipca.ipca_12m,
    i.dividends / s.spending as dividends_cover
from ${ttm_income} as i
cross join (
    select sum(spending) as spending
    from warehouse.monthly_cashflow
    where budget_month >= (select first_month from ${ttm_window})
) as s
left join warehouse.inflation as ipca
    on ipca.month = (select last_month from ${ttm_window})
```

```sql top_source
with w as (select * from ${ttm_window})
select
    c.income_group,
    sum(c.effective_amount) as amount,
    sum(c.effective_amount) / sum(sum(c.effective_amount)) over () as share
from ${closed_credits} as c
cross join w
where c.is_operating and c.budget_month >= w.first_month
group by c.income_group
order by amount desc
limit 1
```

## Last 12 closed months, through <Value data={income_kpis} column=through_month />

<div class="kpi-grid">

<BigValue
    data={income_kpis}
    value=income
    title="Operating income"
    fmt=brl1k
    comparison=income_growth
    comparisonFmt=pct1
    comparisonTitle="vs prior 12 months"
/>
<BigValue
    data={income_kpis}
    value=real_income_growth
    title="Real income growth"
    fmt=pct1
/>
<BigValue
    data={top_source}
    value=share
    title="Share of the largest source"
    fmt=pct0
/>
<BigValue
    data={income_kpis}
    value=dividends
    title="Dividends (passive income)"
    fmt=brl0
/>
<BigValue
    data={income_kpis}
    value=dividends_cover
    title="Share of spending dividends pay for"
    fmt=pct1
/>

</div>

<!-- fmt() instead of <Value>: Value leaves a space before the punctuation that follows it -->
Income {income_kpis[0]?.income_growth >= 0 ? 'grew' : 'fell'} {fmt(Math.abs(income_kpis[0]?.income_growth), 'pct1')} against {fmt(income_kpis[0]?.ipca_12m, 'pct1')} of inflation, so in real terms it {income_kpis[0]?.real_income_growth >= 0 ? 'grew' : 'shrank'} {fmt(Math.abs(income_kpis[0]?.real_income_growth), 'pct1')}. {top_source[0]?.income_group} alone is {fmt(top_source[0]?.share, 'pct0')} of it: the more income depends on one source, the more a single change (a job, a bonus) moves the whole picture.

## Where it comes from

```sql years
-- Closed months per year, to flag the year still in progress
select
    budget_year as year,
    count(*) as closed_months,
    case
        when count(*) < 12 then budget_year || ' (to ' || strftime(max(budget_month), '%b') || ')'
        else budget_year
    end as year_label
from warehouse.monthly_cashflow
group by budget_year
```

```sql by_group
select
    y.year_label,
    c.income_group,
    sum(c.effective_amount) as amount
from ${closed_credits} as c
inner join ${years} as y on c.year = y.year
where c.is_operating
group by y.year_label, c.income_group
order by y.year_label, c.income_group
```

<BarChart
    data={by_group}
    x=year_label
    y=amount
    series=income_group
    seriesOrder={['Salary', 'Variable pay', 'Benefits', 'Business', 'Dividends', 'Other']}
    type=stacked
    sort=false
    yFmt=brl0k
    title="Operating income by source"
/>

Variable pay is profit sharing, the 13th salary and vacation pay; benefits are the meal and other allowances. Dividends start small and grow with the real-estate fund position.

```sql by_owner
select
    y.year_label,
    coalesce(c.owner, 'Other') as owner,
    sum(c.effective_amount) as amount
from ${closed_credits} as c
inner join ${years} as y on c.year = y.year
where c.is_operating
group by y.year_label, owner
order by y.year_label, owner
```

<BarChart
    data={by_owner}
    x=year_label
    y=amount
    series=owner
    seriesOrder={['Person A', 'Person B', 'Other']}
    type=stacked100
    sort=false
    title="Who earns it"
/>

The owner is read from the cell color of each credit. 2021 had no owner colors, so all of it is Person A. "Other" is income with no owner color, mostly fund dividends.

## Income, spending and savings by year

```sql yearly
select
    y.year_label as year,
    y.closed_months,
    sum(m.income) as income,
    sum(m.spending) as spending,
    sum(m.invested) as invested,
    sum(m.savings) as savings,
    sum(m.savings) / sum(m.income) as savings_rate,
    sum(m.non_operating_income) as non_operating_income
from warehouse.monthly_cashflow as m
inner join ${years} as y on m.budget_year = y.year
group by y.year_label, y.closed_months
order by y.year_label
```

<DataTable data={yearly}>
    <Column id=year />
    <Column id=income fmt=brl0 />
    <Column id=spending fmt=brl0 />
    <Column id=savings fmt=brl0 />
    <Column id=savings_rate fmt=pct1 title="Savings rate" />
    <Column id=invested fmt=brl0 title="Into investments" />
    <Column id=non_operating_income fmt=brl0 title="One-off (asset sales)" />
</DataTable>

Savings is income minus spending: what went into investments plus what stayed in the account.

## One-off money

```sql one_off
select
    strftime(budget_month, '%b %Y') as month,
    description,
    effective_amount as amount
from ${closed_credits}
where not is_operating
order by budget_month
```

Credits in the "Investimentos" category come from selling an asset (here, a car sold in installments). They count as cash, but not as income, so they don't inflate the savings rate of the year they land in.

<DataTable data={one_off} emptySet=pass emptyMessage="No one-off credits">
    <Column id=month />
    <Column id=description />
    <Column id=amount fmt=brl0 />
</DataTable>
