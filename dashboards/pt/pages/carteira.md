---
title: Carteira
sidebar_position: 5
---

<!-- Tradução de dashboards/pages/portfolio.md: uma mudança lá vale aqui também -->

A aba de carteira é um registro de snapshots: em uma data de referência, o valor de cada ativo. Cada planilha anual repete o registro inteiro, então o dbt guarda uma cópia de cada snapshot, a da planilha mais recente. Esta página responde duas perguntas: a carteira cresce por **dinheiro novo** ou por **rendimento**, e o rendimento **ganha da inflação**?

```sql worth
-- Snapshot mais recente primeiro (o BigValue mostra a primeira linha). Meio-dia
-- UTC mantém cada data no seu dia em qualquer fuso.
select
    now_.*,
    now_.reference_date + interval 12 hours as snapshot_at,
    strftime(now_.reference_date, '%d/%m/%Y') as reference_label,
    now_.total_value / year_ago.total_value - 1 as value_change_1y
from warehouse.net_worth as now_
asof left join warehouse.net_worth as year_ago
    on now_.reference_date - interval 1 year >= year_ago.reference_date
order by now_.reference_date desc
```

```sql real_return
select
    *,
    reference_date + interval 12 hours as snapshot_at
from warehouse.net_worth
where real_return_12m is not null
order by reference_date desc
```

## Último snapshot, <Value data={worth} column=reference_label />

<div class="kpi-grid">

<BigValue
    data={worth}
    value=total_value
    title="Valor da carteira"
    fmt=brl0
    comparison=value_change_1y
    comparisonFmt=pct1
    comparisonTitle="em um ano"
/>
<BigValue
    data={real_return}
    value=real_return_12m
    title="Retorno real, 12 meses"
    fmt=pct1
    sparkline=snapshot_at
/>
<BigValue
    data={worth}
    value=runway_months
    title="Meses de gastos que ela pagaria"
    fmt=num0
/>
<BigValue
    data={worth}
    value=reserve_months
    title="Reserva, meses de gastos"
    fmt=num1
/>

</div>

## Dinheiro novo ou rendimento?

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
select snapshot_at, 'Valor da carteira' as measure, total_value as amount from ${growth}
union all
select snapshot_at, 'Valor inicial + dinheiro novo' as measure, invested_capital as amount from ${growth}
order by snapshot_at, measure
```

```sql growth_split
select
    list_extract(
        ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'],
        month(min(reference_date))
    ) || '/' || year(min(reference_date)) as since,
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
    seriesOrder={['Valor da carteira', 'Valor inicial + dinheiro novo']}
    seriesColors={{'Valor da carteira': ['#5650d6', '#8a85f0'], 'Valor inicial + dinheiro novo': ['#7b8491', '#5f6873']}}
    yFmt=brl0k
    xFmt="mm/yyyy"
/>

<!-- fmt() em vez de <Value>: o Value deixa um espaço antes da pontuação que vem depois -->
Desde {growth_split[0]?.since}, entraram {fmt(growth_split[0]?.contributions, 'brl0')} de dinheiro novo e a carteira rendeu {fmt(growth_split[0]?.gains, 'brl0')} além disso, proventos incluídos: de tudo o que a carteira ganhou, {fmt(growth_split[0]?.gains_share, 'pct0')} veio do rendimento. A distância entre as duas linhas é esse rendimento.

## Ganhou da inflação?

```sql by_year
-- O último snapshot de cada ano tem o retorno composto do ano e a inflação
-- dos mesmos períodos
select
    case
        when year(reference_date) = year((select min(reference_date) from warehouse.net_worth))
            then strftime(reference_date, '%Y') || ' (desde ' || list_extract(
                ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'],
                month((select min(reference_date) from warehouse.net_worth))
            ) || ')'
        when month(reference_date) < 12
            then strftime(reference_date, '%Y') || ' (até ' || list_extract(
                ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'],
                month(reference_date)
            ) || ')'
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
select year, 'Retorno da carteira' as measure, return_ytd as rate from ${by_year}
union all
select year, 'Inflação (IPCA)' as measure, inflation_ytd as rate from ${by_year}
order by year, measure
```

<BarChart
    data={by_year_long}
    x=year
    y=rate
    series=measure
    seriesOrder={['Retorno da carteira', 'Inflação (IPCA)']}
    seriesColors={{'Retorno da carteira': ['#5650d6', '#8a85f0'], 'Inflação (IPCA)': ['#7b8491', '#5f6873']}}
    type=grouped
    sort=false
    yFmt=pct0
    labels=true
    labelFmt=pct1
/>

<DataTable data={by_year}>
    <Column id=year title="Ano" />
    <Column id=return_ytd fmt=pct1 title="Retorno" />
    <Column id=inflation_ytd fmt=pct1 title="Inflação (IPCA)" />
    <Column id=real_return_ytd fmt=pct1 title="Retorno real" contentType=delta />
</DataTable>

```sql rolling
select reference_date + interval 12 hours as snapshot_at, 'Retorno da carteira' as measure, return_12m as rate
from warehouse.net_worth where return_12m is not null
union all
select reference_date + interval 12 hours, 'Inflação (IPCA)', inflation_12m
from warehouse.net_worth where return_12m is not null
order by snapshot_at, measure
```

<LineChart
    data={rolling}
    x=snapshot_at
    y=rate
    series=measure
    seriesOrder={['Retorno da carteira', 'Inflação (IPCA)']}
    seriesColors={{'Retorno da carteira': ['#5650d6', '#8a85f0'], 'Inflação (IPCA)': ['#7b8491', '#5f6873']}}
    yFmt=pct0
    xFmt="mm/yyyy"
    title="Acumulado em 12 meses"
/>

O objetivo é ganho real: render mais que a inflação, para o dinheiro comprar mais a cada ano. O retorno de cada período entre dois snapshots é o ganho sobre o capital médio, com o dinheiro novo contando por metade do período (Dietz modificado), e a inflação é composta nos mesmos períodos. O dinheiro novo vem da poupança de cada mês fechado, então um mês que gasta mais do que ganha conta como resgate, e o período que chega ao mês corrente fica sem retorno até o mês fechar. Os depósitos do FGTS não são lançados nas planilhas, então aparecem como rendimento.

## Reserva de liquidez

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
    xFmt="mm/yyyy"
    title="Meses de gastos que a reserva cobre"
>
    <ReferenceArea yMin=6 yMax=12 label="Meta: 6 a 12 meses" color=positive opacity=0.35 />
</LineChart>

A reserva é tudo o que dá para sacar no mesmo dia (a lista está em [Metas](/metas)), dividido pelo gasto médio mensal dos últimos 12 meses: por quanto tempo ela manteria a casa, com tudo o que ela gasta, se a renda parasse. Abaixo de 6 meses está curta; acima de 12, há dinheiro parado que poderia render mais em outro lugar.

## Por classe de ativo

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
    seriesOrder={['Renda fixa', 'Multimercado', 'FII', 'Cripto', 'Saldo em conta', 'Outros']}
    type=stacked
    yFmt=brl0k
    xFmt="mm/yyyy"
/>

## Quando a renda fixa vence

```sql ladder
-- Renda fixa no último snapshot, por ano de vencimento
select
    coalesce(strftime(maturity_date, '%Y'), 'Liquidez diária') as maturity,
    coalesce(year(maturity_date), 0) as sort_key,
    sum(gross_value) as value,
    count(*) as holdings
from warehouse.portfolio
where reference_date = (select max(reference_date) from warehouse.portfolio)
    and asset_class = 'Renda fixa'
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

Quando cada parte da renda fixa volta a ficar disponível, e quanto vai precisar ser reinvestido a cada ano.

## Concentração

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

<BigValue data={top_assets} value=top_bank_share title="Peso da maior instituição" fmt=pct0 />
<BigValue data={top_assets} value=top5_share title="Peso dos 5 maiores ativos" fmt=pct0 />

</div>

<DataTable data={by_bank}>
    <Column id=bank title="Instituição" />
    <Column id=value fmt=brl0 title="Valor" contentType=bar barColor={['#dcdafb', '#353094']} />
    <Column id=share fmt=pct1 title="Participação" />
    <Column id=holdings title="Ativos" />
</DataTable>

## Proventos

```sql dividends
-- No meio do mês, para nenhum fuso empurrar uma barra para o mês anterior
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
    xFmt="mm/yyyy"
    title="Proventos de FII por mês"
/>

## Ativos no último snapshot

```sql holdings
select
    bank,
    asset,
    asset_class,
    gross_value,
    gross_value / sum(gross_value) over () as share,
    -- formatado aqui: a tabela mostra uma data NULL como 1969 quando recebe um formato
    coalesce(strftime(maturity_date, '%d/%m/%Y'), '') as maturity
from warehouse.portfolio
where reference_date = (select max(reference_date) from warehouse.portfolio)
order by gross_value desc
```

<DataTable data={holdings} rows=all>
    <Column id=bank title="Banco" />
    <Column id=asset title="Ativo" />
    <Column id=asset_class title="Classe" />
    <Column id=gross_value fmt=brl title="Valor" contentType=bar barColor={['#dcdafb', '#353094']} />
    <Column id=share fmt=pct1 title="Participação" />
    <Column id=maturity title="Vencimento" />
</DataTable>
