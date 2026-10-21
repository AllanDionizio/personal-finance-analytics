---
title: Gastos
sidebar_position: 3
---

<!-- Tradução de dashboards/pages/spending.md: uma mudança lá vale aqui também -->

Para onde vai o dinheiro. Gastos são os débitos efetivados em meses fechados. Dinheiro que vai para investimentos não é gasto, então fica de fora (ele aparece como poupança no [resumo](/)).

```sql ttm_window
select
    max(budget_month) as last_month,
    list_extract(
        ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'],
        month(max(budget_month))
    ) || '/' || year(max(budget_month)) as through_month
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
-- o IPCA mais recente até o fim da janela: o seed pode ficar atrás dos meses fechados
left join warehouse.inflation as ipca
    on ipca.month = (select max(month) from warehouse.inflation where month <= w.last_month)
```

## Últimos 12 meses fechados, até <Value data={spending_kpis} column=through_month />

<div class="kpi-grid">

<BigValue
    data={spending_kpis}
    value=spending
    title="Gastos"
    fmt=brl1k
    comparison=spending_growth
    comparisonFmt=pct1
    comparisonTitle="vs 12 meses anteriores"
    downIsGood=true
/>
<BigValue
    data={spending_kpis}
    value=real_spending_growth
    title="Crescimento real dos gastos"
    fmt=pct1
/>
<BigValue
    data={spending_kpis}
    value=fixed_share
    title="Parte fixa dos gastos"
    fmt=pct1
/>

</div>

<!-- fmt() em vez de <Value>: o Value deixa um espaço antes da pontuação que vem depois -->
Os gastos {spending_kpis[0]?.spending_growth >= 0 ? 'subiram' : 'caíram'} {fmt(Math.abs(spending_kpis[0]?.spending_growth), 'pct1')} contra {fmt(spending_kpis[0]?.ipca_12m, 'pct1')} de inflação: em termos reais, a casa gastou {fmt(Math.abs(spending_kpis[0]?.real_spending_growth), 'pct1')} {spending_kpis[0]?.real_spending_growth >= 0 ? 'a mais' : 'a menos'} que um ano antes.

## O que mudou nos últimos 12 meses

```sql movers
-- As dez categorias cujo gasto mais mudou, últimos 12 meses fechados contra
-- os 12 anteriores
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
    case when coalesce(current_12m, 0) >= coalesce(prior_12m, 0) then 'Subiu' else 'Caiu' end as direction
from by_category
order by abs(coalesce(current_12m, 0) - coalesce(prior_12m, 0)) desc
limit 10
```

<BarChart
    data={movers}
    x=category
    y=change
    series=direction
    seriesColors={{'Subiu': ['#e34948', '#e66767'], 'Caiu': ['#5650d6', '#8a85f0']}}
    swapXY=true
    leftPadding=24
    sort=false
    yFmt=brl0
    title="Variação do gasto por categoria, vs 12 meses anteriores"
/>

<DataTable data={movers}>
    <Column id=category title="Categoria" />
    <Column id=prior_12m fmt=brl0 title="12 meses anteriores" />
    <Column id=current_12m fmt=brl0 title="Últimos 12 meses" />
    <Column id=change fmt=brl0 title="Variação" contentType=delta downIsGood=true />
</DataTable>

## Os gastos crescem mais que a renda e a inflação?

```sql pace
-- Renda e gastos acumulados em 12 meses, e o nível médio de preços nos mesmos
-- 12 meses, cada um com base 100 na primeira janela completa
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
-- no meio do mês, para nenhum fuso empurrar um ponto para o mês anterior
select c.budget_month + interval 14 days as month, 'Renda' as measure,
    100 * c.income_12m / b.income_12m as index
from complete as c cross join base as b
union all
select c.budget_month + interval 14 days, 'Gastos', 100 * c.spending_12m / b.spending_12m
from complete as c cross join base as b
union all
select c.budget_month + interval 14 days, 'Inflação (IPCA)', 100 * c.price_12m / b.price_12m
from complete as c cross join base as b
order by month, measure
```

<LineChart
    data={pace}
    x=month
    y=index
    series=measure
    seriesOrder={['Renda', 'Gastos', 'Inflação (IPCA)']}
    seriesColors={{'Renda': ['#5650d6', '#8a85f0'], 'Gastos': ['#e07a2e', '#d9752a'], 'Inflação (IPCA)': ['#7b8491', '#5f6873']}}
    yFmt=num0
    xFmt="mm/yyyy"
    title="Acumulado em 12 meses, base 100 na primeira janela completa"
/>

Quando a linha de gastos sobe mais rápido que a inflação, a casa está comprando mais, não só pagando preços mais altos. Quando sobe mais rápido que a renda, a taxa de poupança encolhe.

## Custos fixos e variáveis

```sql fixed_variable
-- Meses desenhados no meio do mês: uma data à meia-noite UTC aparece como o dia
-- (e o mês) anterior em navegadores a oeste de UTC; o meio do mês não cruza.
select budget_month + interval 14 days as month, 'Fixo' as macro_category, fixed_spending as amount
from warehouse.monthly_cashflow
union all
select budget_month + interval 14 days as month, 'Variável' as macro_category, variable_spending as amount
from warehouse.monthly_cashflow
union all
-- categorias sem macrocategoria; só aparecem nos meses que têm alguma
select budget_month + interval 14 days as month, 'Sem classificação' as macro_category, unclassified_spending as amount
from warehouse.monthly_cashflow
where unclassified_spending <> 0
order by month, macro_category
```

<BarChart
    data={fixed_variable}
    x=month
    y=amount
    series=macro_category
    seriesOrder={['Fixo', 'Variável', 'Sem classificação']}
    type=stacked
    yFmt=brl0k
    xFmt="mm/yyyy"
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
    <Column id=year title="Ano" />
    <Column id=fixed_spending fmt=brl0 title="Fixo" />
    <Column id=variable_spending fmt=brl0 title="Variável" />
    <Column id=fixed_share fmt=pct1 title="Parte fixa" />
</DataTable>

## Por categoria

```sql years
select distinct budget_year as year
from warehouse.monthly_cashflow
order by year desc
```

<Dropdown
    data={years}
    name=year
    value=year
    title="Ano"
/>

```sql spending_rows
-- Só débitos de meses fechados, o mesmo corte de monthly_cashflow.
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
    title="10 maiores categorias em {inputs.year.value}"
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
    <Column id=category title="Categoria" />
    <Column id=macro_category title="Tipo" />
    <Column id=amount fmt=brl0 title="Valor" contentType=bar barColor={['#dcdafb', '#353094']} />
    <Column id=transactions title="Lançamentos" />
</DataTable>

### Por forma de pagamento

O cartão vem da cor da célula de cada débito. "Outros" é qualquer débito cuja célula não tem cor de cartão.

<DataTable data={by_card} emptySet=pass>
    <Column id=payment_method title="Forma de pagamento" />
    <Column id=amount fmt=brl0 title="Valor" />
    <Column id=share fmt=pct1 title="Participação" />
</DataTable>
