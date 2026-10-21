---
title: Receitas
sidebar_position: 2
---

<!-- Tradução de dashboards/pages/income.md: uma mudança lá vale aqui também -->

De onde vem o dinheiro. Renda aqui é **renda operacional**: o que foi ganho, do salário aos proventos. Dinheiro da venda de um ativo é entrada de caixa de verdade, mas não se repete, então fica à parte (veja o fim da página).

```sql closed_credits
-- Créditos efetivados em meses fechados, com o grupo de origem
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
    list_extract(
        ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'],
        month(max(budget_month))
    ) || '/' || year(max(budget_month)) as through_month
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
        where c.income_group = 'Proventos' and c.budget_month >= w.first_month
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
-- o IPCA mais recente até o fim da janela: o seed pode ficar atrás dos meses fechados
left join warehouse.inflation as ipca
    on ipca.month = (
        select max(month) from warehouse.inflation
        where month <= (select last_month from ${ttm_window})
    )
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

## Últimos 12 meses fechados, até <Value data={income_kpis} column=through_month />

<div class="kpi-grid">

<BigValue
    data={income_kpis}
    value=income
    title="Renda operacional"
    fmt=brl1k
    comparison=income_growth
    comparisonFmt=pct1
    comparisonTitle="vs 12 meses anteriores"
/>
<BigValue
    data={income_kpis}
    value=real_income_growth
    title="Crescimento real da renda"
    fmt=pct1
/>
<BigValue
    data={top_source}
    value=share
    title="Peso da maior fonte"
    fmt=pct0
/>
<BigValue
    data={income_kpis}
    value=dividends
    title="Proventos (renda passiva)"
    fmt=brl0
/>
<BigValue
    data={income_kpis}
    value=dividends_cover
    title="Parte dos gastos que os proventos pagam"
    fmt=pct1
/>

</div>

<!-- fmt() em vez de <Value>: o Value deixa um espaço antes da pontuação que vem depois -->
A renda {income_kpis[0]?.income_growth >= 0 ? 'subiu' : 'caiu'} {fmt(Math.abs(income_kpis[0]?.income_growth), 'pct1')} contra {fmt(income_kpis[0]?.ipca_12m, 'pct1')} de inflação, então em termos reais ela {income_kpis[0]?.real_income_growth >= 0 ? 'cresceu' : 'encolheu'} {fmt(Math.abs(income_kpis[0]?.real_income_growth), 'pct1')}. Só {top_source[0]?.income_group} responde por {fmt(top_source[0]?.share, 'pct0')} dela: quanto mais a renda depende de uma fonte, mais uma única mudança (um emprego, um bônus) mexe no quadro todo.

## De onde vem

```sql years
-- Meses fechados por ano, para marcar o ano ainda em andamento
select
    budget_year as year,
    count(*) as closed_months,
    case
        when count(*) < 12 then budget_year || ' (até ' || list_extract(
            ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'],
            month(max(budget_month))
        ) || ')'
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
    seriesOrder={['Salário', 'Remuneração variável', 'Benefícios', 'Empresa', 'Proventos', 'Outros']}
    type=stacked
    sort=false
    yFmt=brl0k
    title="Renda operacional por fonte"
/>

Remuneração variável é PLR, 13º, férias e comissão; benefícios são os vales e auxílios.

```sql by_owner
select
    y.year_label,
    coalesce(c.owner, 'Outros') as owner,
    sum(c.effective_amount) as amount
from ${closed_credits} as c
inner join ${years} as y on c.year = y.year
where c.is_operating
group by y.year_label, owner
order by y.year_label, owner = 'Outros', owner
```

<BarChart
    data={by_owner}
    x=year_label
    y=amount
    series=owner
    type=stacked100
    sort=false
    title="Quem ganha"
/>

A pessoa vem da cor da célula de cada crédito. Em 2021 as receitas ainda não tinham cor por pessoa, então tudo ficou com uma só. "Outros" é renda sem cor de pessoa, em geral proventos de fundos.

## Renda, gastos e poupança por ano

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
order by y.year_label desc
```

<DataTable data={yearly}>
    <Column id=year title="Ano" />
    <Column id=income fmt=brl0 title="Renda" />
    <Column id=spending fmt=brl0 title="Gastos" />
    <Column id=savings fmt=brl0 title="Poupança" />
    <Column id=savings_rate fmt=pct1 title="Taxa de poupança" />
    <Column id=invested fmt=brl0 title="Aportes" />
    <Column id=non_operating_income fmt=brl0 title="Eventual (venda de ativos)" />
</DataTable>

Poupança é renda menos gastos: o que foi para investimentos mais o que ficou na conta.

## Dinheiro eventual

```sql one_off
select
    list_extract(
        ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'],
        month(budget_month)
    ) || '/' || year(budget_month) as month,
    description,
    effective_amount as amount
from ${closed_credits}
where not is_operating
order by budget_month desc
```

Créditos na categoria "Investimentos" vêm da venda de um ativo. Contam como caixa, mas não como renda, para não inflar a taxa de poupança do ano em que caem.

<DataTable data={one_off} emptySet=pass emptyMessage="Nenhum crédito eventual">
    <Column id=month title="Mês" />
    <Column id=description title="Descrição" />
    <Column id=amount fmt=brl0 title="Valor" />
</DataTable>
