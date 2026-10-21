-- One row per month, from the first portfolio snapshot to the independence
-- target month: the portfolio's value in today's money, the new money
-- against its goal, and two projections from the newest snapshot, at the
-- pace independence needs and at the current pace (fct_goals).
--
-- Past values are brought to today's money with the price index of their
-- month; a month the IPCA seed doesn't reach yet takes the newest index.

with

goals as (

    select * from {{ ref('fct_goals') }}

),

bounds as (

    select cast(date_trunc('month', min(reference_date)) as date) as first_month
    from {{ ref('fct_net_worth') }}

),

months as (

    select
        cast(
            unnest(generate_series(bounds.first_month, goals.fi_target_month, interval 1 month))
            as date
        ) as month
    from bounds
    cross join goals

),

month_end_values as (

    select
        cast(date_trunc('month', reference_date) as date) as month,
        arg_max(total_value, reference_date) as total_value
    from {{ ref('fct_net_worth') }}
    group by 1

),

latest_price as (

    select price_index
    from {{ ref('fct_inflation_monthly') }}
    qualify month = max(month) over ()

),

priced as (

    select
        months.month,
        month_end_values.total_value,
        cashflow.new_money,
        coalesce(
            last_value(inflation.price_index ignore nulls) over (order by months.month),
            latest_price.price_index
        ) as price_index,
        latest_price.price_index as today_price_index
    from months
    cross join latest_price
    left join month_end_values on months.month = month_end_values.month
    left join {{ ref('fct_monthly_cashflow') }} as cashflow
        on months.month = cashflow.budget_month
    left join {{ ref('fct_inflation_monthly') }} as inflation
        on months.month = inflation.month

),

projected as (

    select
        priced.*,
        goals.fi_target_value,
        goals.required_monthly_new_money,
        goals.current_monthly_new_money,
        goals.wealth,
        goals.monthly_return,
        date_diff('month', goals.projection_from, priced.month) as months_ahead
    from priced
    cross join goals

)

select
    month,
    total_value * today_price_index / price_index as wealth_today_money,
    new_money,
    {{ new_money_goal('month', 'required_monthly_new_money') }} as new_money_goal,
    fi_target_value,
    case
        when months_ahead >= 0
            then
                wealth * pow(1 + monthly_return, months_ahead)
                + required_monthly_new_money
                * (pow(1 + monthly_return, months_ahead) - 1) / monthly_return
    end as required_path,
    case
        when months_ahead >= 0
            then
                wealth * pow(1 + monthly_return, months_ahead)
                + current_monthly_new_money
                * (pow(1 + monthly_return, months_ahead) - 1) / monthly_return
    end as current_pace_path
from projected
