---
title: Installments
sidebar_position: 4
---

The workbooks only show the installments that fall inside their own years, so a purchase made late in the newest year has installments that appear nowhere. dbt rebuilds each purchase's full plan from the installments it does find, so this page can answer how much is still owed and until when.

An installment counts as paid when its month comes before the newest month with paid entries. From that month on, the workbook's paid flag decides.

```sql summary
select
    sum(outstanding_amount) as owed,
    count(distinct purchase_id) filter (where outstanding_amount > 0) as open_purchases,
    strftime(max(budget_month) filter (where outstanding_amount > 0), '%b %Y') as paid_off_in,
    -- against the average monthly income of the last 12 closed months
    sum(outstanding_amount) / (
        select sum(income) / 12
        from (select income from warehouse.monthly_cashflow order by budget_month desc limit 12)
    ) as months_of_income
from warehouse.installments
```

<BigValue data={summary} value=owed title="Still owed" fmt=brl />
<BigValue data={summary} value=months_of_income title="In months of income" fmt=num1 />
<BigValue data={summary} value=open_purchases title="Open purchases" />
<BigValue data={summary} value=paid_off_in title="Last installment" />

## What is due each month

```sql due_by_month
select
    budget_month,
    strftime(budget_month, '%b %Y') as month,
    sum(outstanding_amount) as owed,
    count(*) as installments
from warehouse.installments
where outstanding_amount > 0
group by budget_month
order by budget_month
```

<BarChart
    data={due_by_month}
    x=month
    y=owed
    yFmt=brl0
    sort=false
    labels=true
    labelFmt=brl0
/>

## Open purchases

```sql open_purchases
select
    description,
    any_value(category) as category,
    any_value(payment_method) as payment_method,
    max(installment_count) as installment_count,
    count(*) filter (where outstanding_amount = 0) as paid_installments,
    max(amount) as installment_amount,
    sum(outstanding_amount) as owed,
    -- formatted here: a date column would show the previous month west of UTC
    strftime(max(budget_month), '%b %Y') as last_month
from warehouse.installments
group by purchase_id, description
having sum(outstanding_amount) > 0
order by owed desc
```

<DataTable data={open_purchases} rows=all>
    <Column id=description title="Purchase" />
    <Column id=category />
    <Column id=payment_method title="Card" />
    <Column id=paid_installments title="Paid" />
    <Column id=installment_count title="Of" />
    <Column id=installment_amount fmt=brl title="Per installment" />
    <Column id=owed fmt=brl title="Still owed" contentType=bar />
    <Column id=last_month title="Last installment" />
</DataTable>

## How much of the spending is in installments

```sql installment_share
select
    strftime(budget_month, '%Y') as year,
    sum(effective_amount) filter (where is_installment) as in_installments,
    sum(effective_amount) as spending,
    sum(effective_amount) filter (where is_installment) / sum(effective_amount) as share
from warehouse.transactions
where side = 'debit'
    and budget_month <= (select max(budget_month) from warehouse.monthly_cashflow)
group by year
order by year
```

<BarChart
    data={installment_share}
    x=year
    y=share
    yFmt=pct0
    labels=true
    labelFmt=pct1
    sort=false
    title="Share of yearly spending paid in installments"
/>
