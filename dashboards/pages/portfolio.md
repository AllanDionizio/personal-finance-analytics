---
title: Portfolio
sidebar_position: 5
---

The portfolio sheet is a log of snapshots: on a reference date, the value of every holding. Each yearly workbook repeats the whole log, so dbt keeps one copy of each snapshot, the one from the newest file. This page asks two questions: does the portfolio grow from **contributions** or from **returns**, and do the returns **beat inflation**?

```sql worth
-- Newest snapshot first (BigValue shows the first row). Noon UTC keeps each
-- date on its calendar day in every browser time zone.
select
    now_.*,
    now_.reference_date + interval 12 hours as snapshot_at,
    strftime(now_.reference_date, '%d %b %Y') as reference_label,
    now_.total_value / year_ago.total_value - 1 as value_change_1y
from warehouse.net_worth as now_
asof left join warehouse.net_worth as year_ago
    on now_.reference_date - interval 1 year >= year_ago.reference_date
order by now_.reference_date desc
```

```sql real_return
select
    *,
    reference_date + interval 12 hours as snapshot_at,
    strftime(reference_date, '%b %Y') as through_month
from warehouse.net_worth
where real_return_12m is not null
order by reference_date desc
```

## Latest snapshot, <Value data={worth} column=reference_label />

<div class="kpi-grid">

<BigValue
    data={worth}
    value=total_value
    title="Portfolio value"
    fmt=brl0
    comparison=value_change_1y
    comparisonFmt=pct1
    comparisonTitle="in a year"
/>
<BigValue
    data={real_return}
    value=real_return_12m
    title="Real return, 12 months"
    fmt=pct1
    sparkline=snapshot_at
/>
<BigValue
    data={worth}
    value=runway_months
    title="Months of spending it would pay for"
    fmt=num0
/>
<BigValue
    data={worth}
    value=reserve_months
    title="Liquid reserve, months of fixed costs"
    fmt=num1
/>

</div>

## Contributions or returns?

```sql growth
select
    reference_date + interval 12 hours as snapshot_at,
    total_value,
    first_value(total_value) over (order by reference_date)
        + coalesce(sum(contributions) over (order by reference_date), 0) as invested_capital
from warehouse.net_worth
order by reference_date
```

```sql growth_long
select snapshot_at, 'Portfolio value' as measure, total_value as amount from ${growth}
union all
select snapshot_at, 'First value + contributions' as measure, invested_capital as amount from ${growth}
order by snapshot_at, measure
```

```sql growth_split
select
    strftime(min(reference_date), '%b %Y') as since,
    sum(contributions) as contributions,
    sum(period_gain) as gains,
    sum(dividends) as dividends,
    sum(period_gain) / (sum(contributions) + sum(period_gain)) as gains_share
from warehouse.net_worth
```

<LineChart
    data={growth_long}
    x=snapshot_at
    y=amount
    series=measure
    seriesOrder={['Portfolio value', 'First value + contributions']}
    seriesColors={{'Portfolio value': ['#5650d6', '#8a85f0'], 'First value + contributions': ['#7b8491', '#5f6873']}}
    yFmt=brl0k
    xFmt="mmm yyyy"
/>

<!-- fmt() instead of <Value>: Value leaves a space before the punctuation that follows it -->
Since {growth_split[0]?.since}, {fmt(growth_split[0]?.contributions, 'brl0')} came in as contributions and the portfolio earned {fmt(growth_split[0]?.gains, 'brl0')} on top (dividends paid into the account included): of everything the portfolio added, {fmt(growth_split[0]?.gains_share, 'pct0')} came from returns. The gap between the two lines is what the market added; dividends are paid out, so they sit outside it.

## Did it beat inflation?

```sql by_year
-- The last snapshot of each year holds that year's compounded return and
-- the inflation over the same periods
select
    case
        when year(reference_date) = year((select min(reference_date) from warehouse.net_worth))
            then strftime(reference_date, '%Y') || ' (from ' || strftime((select min(reference_date) from warehouse.net_worth), '%b') || ')'
        when month(reference_date) < 12
            then strftime(reference_date, '%Y') || ' (to ' || strftime(reference_date, '%b') || ')'
        else strftime(reference_date, '%Y')
    end as year,
    return_ytd,
    inflation_ytd,
    real_return_ytd
from warehouse.net_worth
where return_ytd is not null
qualify reference_date = max(reference_date) over (partition by year(reference_date))
order by reference_date desc
```

```sql by_year_long
select year, 'Portfolio return' as measure, return_ytd as rate from ${by_year}
union all
select year, 'Inflation (IPCA)' as measure, inflation_ytd as rate from ${by_year}
order by year, measure
```

<BarChart
    data={by_year_long}
    x=year
    y=rate
    series=measure
    seriesOrder={['Portfolio return', 'Inflation (IPCA)']}
    seriesColors={{'Portfolio return': ['#5650d6', '#8a85f0'], 'Inflation (IPCA)': ['#7b8491', '#5f6873']}}
    type=grouped
    sort=false
    yFmt=pct0
    labels=true
    labelFmt=pct1
/>

<DataTable data={by_year}>
    <Column id=year />
    <Column id=return_ytd fmt=pct1 title="Return" />
    <Column id=inflation_ytd fmt=pct1 title="Inflation (IPCA)" />
    <Column id=real_return_ytd fmt=pct1 title="Real return" contentType=delta />
</DataTable>

```sql rolling
select reference_date + interval 12 hours as snapshot_at, 'Portfolio return' as measure, return_12m as rate
from warehouse.net_worth where return_12m is not null
union all
select reference_date + interval 12 hours, 'Inflation (IPCA)', inflation_12m
from warehouse.net_worth where return_12m is not null
order by snapshot_at, measure
```

<LineChart
    data={rolling}
    x=snapshot_at
    y=rate
    series=measure
    seriesOrder={['Portfolio return', 'Inflation (IPCA)']}
    seriesColors={{'Portfolio return': ['#5650d6', '#8a85f0'], 'Inflation (IPCA)': ['#7b8491', '#5f6873']}}
    yFmt=pct0
    xFmt="mmm yyyy"
    title="Rolling 12 months"
/>

The goal is a real gain: returning more than inflation, so the money buys more each year. The return of each period between two snapshots is the gain over the average capital, with contributions counted for half the period (modified Dietz), and inflation is compounded over the same periods. Withdrawals aren't recorded in the workbooks, so a period with one would show a lower return than it had, never a higher one.

## Liquid reserve

```sql reserve
select
    reference_date + interval 12 hours as snapshot_at,
    reserve_months
from warehouse.net_worth
where reserve_months is not null
order by reference_date
```

<LineChart
    data={reserve}
    x=snapshot_at
    y=reserve_months
    yFmt=num0
    xFmt="mmm yyyy"
    title="Months of fixed costs the reserve covers"
>
    <ReferenceArea yMin=6 yMax=12 label="Target: 6 to 12 months" color=positive opacity=0.35 />
</LineChart>

The reserve is the cash balance plus fixed income with no maturity date (daily liquidity), divided by the average monthly fixed costs of the last 12 months: how long it would cover the bills that come every month. Below 6 months it is thin; above 12, money is sitting idle that could earn more elsewhere.

## By asset class

```sql by_class
select
    reference_date + interval 12 hours as snapshot_at,
    asset_class,
    sum(gross_value) as value
from warehouse.portfolio
group by reference_date, asset_class
order by reference_date, asset_class
```

<AreaChart
    data={by_class}
    x=snapshot_at
    y=value
    series=asset_class
    seriesOrder={['Fixed income', 'Multimarket fund', 'Real estate fund', 'Crypto', 'Cash', 'Other']}
    type=stacked
    yFmt=brl0k
    xFmt="mmm yyyy"
/>

## When the fixed income matures

```sql ladder
-- Fixed income in the latest snapshot, by maturity year
select
    coalesce(strftime(maturity_date, '%Y'), 'Daily liquidity') as maturity,
    coalesce(year(maturity_date), 0) as sort_key,
    sum(gross_value) as value,
    count(*) as holdings
from warehouse.portfolio
where reference_date = (select max(reference_date) from warehouse.portfolio)
    and asset_class = 'Fixed income'
group by maturity, sort_key
order by sort_key
```

<BarChart
    data={ladder}
    x=maturity
    y=value
    sort=false
    yFmt=brl0k
    labels=true
    labelFmt=brl0k
/>

When each part of the fixed income becomes available again, and what has to be reinvested each year.

## Concentration

```sql by_bank
select
    bank,
    sum(gross_value) as value,
    sum(gross_value) / sum(sum(gross_value)) over () as share,
    count(*) as holdings
from warehouse.portfolio
where reference_date = (select max(reference_date) from warehouse.portfolio)
group by bank
order by value desc
```

```sql top_assets
with latest as (
    select gross_value
    from warehouse.portfolio
    where reference_date = (select max(reference_date) from warehouse.portfolio)
)
select
    (select sum(gross_value) from (select gross_value from latest order by gross_value desc limit 5))
        / (select sum(gross_value) from latest) as top5_share,
    (select max(share) from ${by_bank}) as top_bank_share
```

<div class="kpi-grid">

<BigValue data={top_assets} value=top_bank_share title="Share of the largest institution" fmt=pct0 />
<BigValue data={top_assets} value=top5_share title="Share of the 5 largest holdings" fmt=pct0 />

</div>

<DataTable data={by_bank}>
    <Column id=bank title="Institution" />
    <Column id=value fmt=brl0 contentType=bar barColor={['#dcdafb', '#353094']} />
    <Column id=share fmt=pct1 />
    <Column id=holdings />
</DataTable>

## Dividends

```sql dividends
-- Mid-month, so no browser time zone pushes a bar into the month before
select
    budget_month + interval 14 days as month,
    dividends
from warehouse.monthly_cashflow
where budget_month >= (select min(reference_date) from warehouse.net_worth)
order by month
```

<BarChart
    data={dividends}
    x=month
    y=dividends
    yFmt=brl0
    xFmt="mmm yyyy"
    title="Real-estate fund dividends per month"
/>

## Holdings in the latest snapshot

```sql holdings
select
    bank,
    asset,
    asset_class,
    gross_value,
    gross_value / sum(gross_value) over () as share,
    -- formatted here: the table renders a NULL date as 1969 when given a format
    coalesce(strftime(maturity_date, '%Y-%m-%d'), '') as maturity
from warehouse.portfolio
where reference_date = (select max(reference_date) from warehouse.portfolio)
order by gross_value desc
```

<DataTable data={holdings} rows=all>
    <Column id=bank title="Bank" />
    <Column id=asset title="Asset" />
    <Column id=asset_class title="Class" />
    <Column id=gross_value fmt=brl title="Value" contentType=bar barColor={['#dcdafb', '#353094']} />
    <Column id=share fmt=pct1 title="Share" />
    <Column id=maturity title="Maturity" />
</DataTable>
