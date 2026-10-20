---
title: Portfolio
---

The portfolio sheet is a log of snapshots: on a reference date, the value of every holding. Each yearly workbook repeats the whole log, so dbt keeps one copy of each snapshot, the one from the newest file.

```sql totals
select
    reference_date,
    -- noon UTC stays on the same calendar day in every browser time zone;
    -- a midnight date shows up as the day before west of UTC
    reference_date + interval 12 hours as snapshot_at,
    sum(gross_value) as total
from warehouse.portfolio
group by reference_date
order by reference_date
```

```sql latest
with ranked as (
    select
        *,
        row_number() over (order by reference_date desc) as rank_desc
    from ${totals}
),
year_ago as (
    -- the newest snapshot at least a year older than the latest one
    select total
    from ${totals}
    where reference_date <= (select max(reference_date) from ${totals}) - interval 1 year
    order by reference_date desc
    limit 1
)
select
    ranked.reference_date,
    strftime(ranked.reference_date, '%d %b %Y') as reference_label,
    ranked.total,
    ranked.total / (select total from year_ago) - 1 as change_1y
from ranked
where rank_desc = 1
```

<BigValue
    data={latest}
    value=total
    title="Portfolio value"
    fmt=brl
    comparison=change_1y
    comparisonFmt=pct1
    comparisonTitle="vs a year earlier"
/>
<BigValue data={latest} value=reference_label title="Latest snapshot" />

## Value over time

<AreaChart
    data={totals}
    x=snapshot_at
    y=total
    yFmt=brl0k
    xFmt="mmm yyyy"
/>

The growth mixes new contributions and returns; the sheet doesn't separate them, so neither does this chart.

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
    <Column id=gross_value fmt=brl title="Value" contentType=bar />
    <Column id=share fmt=pct1 title="Share" />
    <Column id=maturity title="Maturity" />
</DataTable>
