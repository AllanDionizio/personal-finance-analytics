---
title: Parcelas
sidebar_position: 4
---

<!-- Tradução de dashboards/pages/installments.md: uma mudança lá vale aqui também -->

Cada planilha só mostra as parcelas que caem dentro do próprio ano, então uma compra feita no fim do ano mais recente tem parcelas que não aparecem em lugar nenhum. O dbt reconstrói o plano completo de cada compra a partir das parcelas que encontra, e assim esta página responde quanto ainda falta pagar e até quando.

Uma parcela conta como paga quando o mês dela vem antes do mês atual de referência. Daí em diante, vale o OK da planilha.

```sql summary
select
    sum(outstanding_amount) as owed,
    count(distinct purchase_id) filter (where outstanding_amount > 0) as open_purchases,
    list_extract(
        ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'],
        month(max(budget_month) filter (where outstanding_amount > 0))
    ) || '/' || year(max(budget_month) filter (where outstanding_amount > 0)) as paid_off_in,
    -- contra a renda média mensal dos últimos 12 meses fechados
    sum(outstanding_amount) / (
        select sum(income) / 12
        from (select income from warehouse.monthly_cashflow order by budget_month desc limit 12)
    ) as months_of_income
from warehouse.installments
```

<div class="kpi-grid">

<BigValue data={summary} value=owed title="Ainda a pagar" fmt=brl />
<BigValue data={summary} value=months_of_income title="Em meses de renda" fmt=num1 />
<BigValue data={summary} value=open_purchases title="Compras em aberto" />
<BigValue data={summary} value=paid_off_in title="Última parcela" />

</div>

## O que vence em cada mês

```sql due_by_month
select
    budget_month,
    list_extract(
        ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'],
        month(budget_month)
    ) || '/' || year(budget_month) as month,
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

## Compras em aberto

```sql open_purchases
select
    description,
    any_value(category) as category,
    any_value(payment_method) as payment_method,
    max(installment_count) as installment_count,
    count(*) filter (where outstanding_amount = 0) as paid_installments,
    max(amount) as installment_amount,
    sum(outstanding_amount) as owed,
    -- formatado aqui: uma coluna de data mostraria o mês anterior a oeste de UTC
    list_extract(
        ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'],
        month(max(budget_month))
    ) || '/' || year(max(budget_month)) as last_month
from warehouse.installments
group by purchase_id, description
having sum(outstanding_amount) > 0
order by owed desc
```

<DataTable data={open_purchases} rows=all>
    <Column id=description title="Compra" />
    <Column id=category title="Categoria" />
    <Column id=payment_method title="Cartão" />
    <Column id=paid_installments title="Pagas" />
    <Column id=installment_count title="De" />
    <Column id=installment_amount fmt=brl title="Por parcela" />
    <Column id=owed fmt=brl title="Ainda a pagar" contentType=bar barColor={['#dcdafb', '#353094']} />
    <Column id=last_month title="Última parcela" />
</DataTable>

## Quanto dos gastos é parcelado

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
    title="Parte dos gastos do ano paga em parcelas"
/>
