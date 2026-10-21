---
title: Metas
sidebar_position: 6
---

<!-- Tradução de dashboards/pages/goals.md: uma mudança lá vale aqui também -->

Três metas: independência financeira, dinheiro novo todo mês e reserva de emergência. Todos os valores estão a preços de hoje. As metas são configurações do projeto (no modo pessoal, o arquivo `.env.real`), não dados das planilhas.

```sql goals
select
    *,
    list_extract(
        ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'],
        month(fi_target_month)
    ) || '/' || year(fi_target_month) as target_label,
    coalesce(
        list_extract(
            ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'],
            month(projected_fi_month)
        ) || '/' || year(projected_fi_month),
        'um prazo fora de vista'
    ) as projected_label,
    greatest(reserve_target - reserve, 0) as reserve_gap
from warehouse.goals
```

## Independência financeira

<div class="kpi-grid">

<BigValue data={goals} value=fi_target_value title="Meta" fmt=brl0 />
<BigValue data={goals} value=fi_progress title="Já alcançado" fmt=pct1 />
<BigValue data={goals} value=required_monthly_new_money title="Dinheiro novo necessário por mês" fmt=brl0 />
<BigValue data={goals} value=current_monthly_new_money title="Dinheiro novo por mês, últimos 12 meses" fmt=brl0 />

</div>

<!-- fmt() em vez de <Value>: o Value deixa um espaço antes da pontuação que vem depois -->
Independência é a carteira pagar o custo de vida para sempre: {fmt(goals[0]?.fi_monthly_spending, 'brl0')} por mês, retirando {fmt(goals[0]?.fi_withdrawal_rate, 'pct0')} dela ao ano, pedem {fmt(goals[0]?.fi_target_value, 'brl0')}. Rendendo {fmt(goals[0]?.fi_real_return, 'pct1')} ao ano acima da inflação, a carteira chega lá em {goals[0]?.target_label} com {fmt(goals[0]?.required_monthly_new_money, 'brl0')} de dinheiro novo por mês. No ritmo dos últimos 12 meses, chega em **{goals[0]?.projected_label}**.

```sql fi_paths
-- No meio do mês, para nenhum fuso empurrar um ponto para o mês anterior
select month + interval 14 days as month, 'Valor da carteira' as measure, wealth_today_money as amount
from warehouse.goal_tracking where wealth_today_money is not null
union all
select month + interval 14 days, 'Caminho até a meta', required_path
from warehouse.goal_tracking where required_path is not null
union all
select month + interval 14 days, 'No ritmo atual', current_pace_path
from warehouse.goal_tracking where current_pace_path is not null
order by month, measure
```

<LineChart
    data={fi_paths}
    x=month
    y=amount
    series=measure
    seriesOrder={['Valor da carteira', 'Caminho até a meta', 'No ritmo atual']}
    seriesColors={{'Valor da carteira': ['#5650d6', '#8a85f0'], 'Caminho até a meta': ['#7b8491', '#5f6873'], 'No ritmo atual': ['#e07a2e', '#d9752a']}}
    yFmt=brl0k
    xFmt="yyyy"
>
    <ReferenceLine y={goals[0]?.fi_target_value} label="Meta" color=positive />
</LineChart>

## Dinheiro novo todo mês

```sql new_money
-- Dois anos para trás e dois para a frente, para os próximos degraus da meta aparecerem
select
    month + interval 14 days as month,
    -- nomes para a legenda
    new_money as dinheiro_novo,
    new_money_goal as meta
from warehouse.goal_tracking
cross join (select projection_from from warehouse.goals) as g
where month between g.projection_from - interval 24 months and g.projection_from + interval 24 months
order by month
```

<Chart data={new_money} x=month yFmt=brl0 xFmt="mm/yyyy">
    <Bar y=dinheiro_novo />
    <Line y=meta step=true />
</Chart>

Dinheiro novo é o que entra no patrimônio vindo de fora da carteira, mês a mês: a poupança mais as vendas de bens, menos os proventos. A meta sobe todo ano até o que a independência pede. Um mês pontual, como uma doação ou a venda de um bem, puxa a média de 12 meses para cima durante um ano inteiro.

## Reserva de emergência

<div class="kpi-grid">

<BigValue data={goals} value=reserve title="Reserva" fmt=brl0 />
<BigValue data={goals} value=reserve_target title="Meta" fmt=brl0 />
<BigValue data={goals} value=reserve_progress title="Já alcançado" fmt=pct0 />
<BigValue data={goals} value=reserve_gap title="Falta guardar" fmt=brl0 />

</div>

A meta é de 6 meses do gasto médio da casa, guardados onde dá para sacar no mesmo dia (veja a [Carteira](/carteira)).
