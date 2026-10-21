---
title: Finanças da casa
sidebar_position: 1
---

<!-- Tradução de dashboards/pages/index.md: uma mudança lá vale aqui também -->

```sql ttm
-- Últimos 12 meses fechados contra os 12 anteriores. O mês ainda em aberto
-- não está em monthly_cashflow, então um mês parcial nunca puxa os totais.
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
    list_extract(
        ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'],
        month(max(budget_month))
    ) || '/' || year(max(budget_month)) as through_month
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
-- Snapshot mais recente primeiro: o BigValue mostra a primeira linha e desenha
-- a sparkline com todas. Meio-dia UTC mantém cada data no seu dia em qualquer fuso.
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
-- O snapshot mais recente cujo retorno de 12 meses dá para comparar com a inflação
select
    *,
    reference_date + interval 12 hours as snapshot_at,
    list_extract(
        ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'],
        month(reference_date)
    ) || '/' || year(reference_date) as through_month
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

<!-- fmt() em vez de <Value>: o Value deixa um espaço antes da pontuação que vem depois -->

<div class="hero">

Nos 12 meses até **{kpis[0]?.through_month}**, a casa recebeu **{fmt(kpis[0]?.income, 'brl0')}**, gastou **{fmt(kpis[0]?.spending, 'brl0')}** e guardou **{fmt(kpis[0]?.savings_rate, 'pct1')}** da renda.

A carteira vale **{fmt(worth[0]?.total_value, 'brl0')}**, {fmt(Math.abs(worth[0]?.value_change_1y), 'pct1')} {worth[0]?.value_change_1y >= 0 ? 'a mais' : 'a menos'} que um ano antes. Nos 12 meses até {real_return[0]?.through_month}, rendeu {fmt(real_return[0]?.return_12m, 'pct1')} contra {fmt(real_return[0]?.inflation_12m, 'pct1')} de inflação (IPCA): {#if real_return[0]?.real_return_12m >= 0}um ganho real de **{fmt(real_return[0]?.real_return_12m, 'pct1')}**{:else}uma **perda** real de {fmt(Math.abs(real_return[0]?.real_return_12m), 'pct1')}{/if}.

A reserva de liquidez cobre **{fmt(worth[0]?.reserve_months, 'num1')} meses** de custos fixos ({worth[0]?.reserve_status?.toLowerCase()}: 6 a 12 meses). As parcelas ainda a pagar somam **{fmt(owed[0]?.owed, 'brl0')}**, cerca de {fmt(owed[0]?.months_of_income, 'num1')} meses de renda.

</div>

<div class="kpi-grid">

<BigValue
    data={worth}
    value=total_value
    title="Carteira"
    fmt=brl1k
    comparison=value_change_1y
    comparisonFmt=pct1
    comparisonTitle="em um ano"
    sparkline=snapshot_at
    sparklineType=area
    link="/carteira"
/>
<BigValue
    data={kpis}
    value=savings_rate
    title="Taxa de poupança, 12 meses"
    fmt=pct1
    comparison=savings_rate_change_pts
    comparisonFmt=num1
    comparisonTitle="p.p. vs 12 meses anteriores"
/>
<BigValue
    data={real_return}
    value=real_return_12m
    title="Retorno real, 12 meses"
    fmt=pct1
    sparkline=snapshot_at
    link="/carteira"
/>
<BigValue
    data={kpis}
    value=fixed_share
    title="Custos fixos, % da renda"
    fmt=pct1
    comparison=fixed_share_change_pts
    comparisonFmt=num1
    comparisonTitle="p.p. vs 12 meses anteriores"
    downIsGood=true
    link="/gastos"
/>
<BigValue
    data={worth}
    value=reserve_months
    title="Reserva, meses de custos fixos"
    fmt=num1
    sparkline=snapshot_at
    link="/carteira"
/>
<BigValue
    data={owed}
    value=owed
    title="Ainda a pagar em parcelas"
    fmt=brl0
    link="/parcelas"
/>

</div>

## Resultado do mês

```sql monthly_result
-- Meses desenhados no meio do mês: uma data à meia-noite UTC aparece como o dia
-- (e o mês) anterior em navegadores a oeste de UTC; o meio do mês não cruza.
select
    budget_month + interval 14 days as month,
    savings as result,
    case when savings >= 0 then 'Superávit' else 'Déficit' end as outcome
from warehouse.monthly_cashflow
order by month
```

<BarChart
    data={monthly_result}
    x=month
    y=result
    series=outcome
    seriesColors={{'Superávit': ['#5650d6', '#8a85f0'], 'Déficit': ['#e34948', '#e66767']}}
    yFmt=brl0k
    xFmt="mm/yyyy"
/>

Renda menos gastos, mês a mês. O superávit é o que paga os aportes da página [Carteira](/carteira).

## O resto da história

<div class="chapters">

- **[Receitas](/receitas)** De onde vem o dinheiro, e quanto é salário, remuneração variável ou proventos
- **[Gastos](/gastos)** Para onde ele vai, o que mudou no último ano e se os gastos crescem mais que a renda e a inflação
- **[Parcelas](/parcelas)** Quanto do futuro já está comprometido
- **[Carteira](/carteira)** Se a carteira cresce por aportes ou por rendimento, e se ganha da inflação

</div>

<small>Um mês só entra nos números depois de fechado.</small>
