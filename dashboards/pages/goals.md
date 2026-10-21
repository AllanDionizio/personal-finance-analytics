---
title: Goals
sidebar_position: 6
---

Three goals: financial independence, new money every month, and a liquid reserve. Every amount is in today's money. The targets are project settings (dbt vars), not data from the workbooks.

```sql goals
select
    *,
    strftime(fi_target_month, '%b %Y') as target_label,
    coalesce(strftime(projected_fi_month, '%b %Y'), 'Not in sight') as projected_label,
    greatest(reserve_target - reserve, 0) as reserve_gap
from warehouse.goals
```

## Financial independence

<div class="kpi-grid">

<BigValue data={goals} value=fi_target_value title="Target" fmt=brl0 />
<BigValue data={goals} value=fi_progress title="Reached" fmt=pct1 />
<BigValue data={goals} value=required_monthly_new_money title="New money needed a month" fmt=brl0 />
<BigValue data={goals} value=current_monthly_new_money title="New money a month, last 12 months" fmt=brl0 />

</div>

<!-- fmt() instead of <Value>: Value leaves a space before the punctuation that follows it -->
Independence means the portfolio pays the cost of living for good: {fmt(goals[0]?.fi_monthly_spending, 'brl0')} a month, withdrawing {fmt(goals[0]?.fi_withdrawal_rate, 'pct0')} of it a year, needs {fmt(goals[0]?.fi_target_value, 'brl0')}. Growing {fmt(goals[0]?.fi_real_return, 'pct1')} a year above inflation, the portfolio gets there by {goals[0]?.target_label} with {fmt(goals[0]?.required_monthly_new_money, 'brl0')} of new money a month. At the pace of the last 12 months it gets there in **{goals[0]?.projected_label}**.

```sql fi_paths
-- Mid-month, so no time zone pushes a point into the previous month
select month + interval 14 days as month, 'Portfolio value' as measure, wealth_today_money as amount
from warehouse.goal_tracking where wealth_today_money is not null
union all
select month + interval 14 days, 'Path to the target', required_path
from warehouse.goal_tracking where required_path is not null
union all
select month + interval 14 days, 'At the current pace', current_pace_path
from warehouse.goal_tracking where current_pace_path is not null
order by month, measure
```

<LineChart
    data={fi_paths}
    x=month
    y=amount
    series=measure
    seriesOrder={['Portfolio value', 'Path to the target', 'At the current pace']}
    seriesColors={{'Portfolio value': ['#5650d6', '#8a85f0'], 'Path to the target': ['#7b8491', '#5f6873'], 'At the current pace': ['#e07a2e', '#d9752a']}}
    yFmt=brl0k
    xFmt="yyyy"
>
    <ReferenceLine y={goals[0]?.fi_target_value} label="Target" color=positive />
</LineChart>

## New money every month

```sql new_money
-- Two years back and two ahead, so the goal's next steps show
select
    month + interval 14 days as month,
    -- named for the legend
    new_money,
    new_money_goal as goal
from warehouse.goal_tracking
cross join (select projection_from from warehouse.goals) as g
where month between g.projection_from - interval 24 months and g.projection_from + interval 24 months
order by month
```

<Chart data={new_money} x=month yFmt=brl0 xFmt="mmm yyyy">
    <Bar y=new_money />
    <Line y=goal step=true />
</Chart>

New money is what enters the household's wealth from outside the portfolio, month by month. The goal rises every year up to what independence needs. A one-off month, such as a gift or an asset sale, lifts the 12-month average for a whole year after it.

## Liquid reserve

<div class="kpi-grid">

<BigValue data={goals} value=reserve title="Reserve" fmt=brl0 />
<BigValue data={goals} value=reserve_target title="Target" fmt=brl0 />
<BigValue data={goals} value=reserve_progress title="Reached" fmt=pct0 />
<BigValue data={goals} value=reserve_gap title="Still to put aside" fmt=brl0 />

</div>

The target is 6 months of the household's average spending, kept where it can be withdrawn the same day (see [Portfolio](/portfolio)).
