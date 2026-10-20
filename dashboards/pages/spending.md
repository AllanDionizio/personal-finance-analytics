---
title: Spending
---

Spending counts settled debits in closed months. Money moved into investments is not spending, so it is left out (it shows up as savings on the [overview](/)).

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
