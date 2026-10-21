-- One row: where the household stands against its goals, from the newest
-- portfolio snapshot.
--
-- Financial independence: the portfolio pays the cost of living for good
-- when a yearly withdrawal of fi_withdrawal_rate covers it, so the target is
-- the yearly cost of living over that rate. The cost of living is var
-- fi_monthly_spending or, without it, the last 12 closed months' average
-- spending. The projections grow the portfolio by fi_real_return a year
-- above inflation, so every amount is in today's money. The current pace is
-- the last 12 closed months' average new money.
--
-- The reserve goal is reserve_min_months of the average monthly spending.

with

latest as (

    select
        reference_date,
        total_value,
        liquid_reserve,
        avg_monthly_spending
    from {{ ref('fct_net_worth') }}
    qualify reference_date = max(reference_date) over ()

),

recent_months as (

    select
        spending,
        new_money
    from {{ ref('fct_monthly_cashflow') }}
    qualify row_number() over (order by budget_month desc) <= 12

),

last_12 as (

    select
        avg(spending) as avg_spending,
        avg(new_money) as avg_new_money
    from recent_months

),

params as (

    select
        latest.*,
        last_12.avg_new_money,
        cast(date_trunc('month', latest.reference_date) as date) as projection_from,
        cast('{{ var("fi_target_month") }}' as date) as fi_target_month,
        coalesce(
            try_cast(
                nullif('{{ var("fi_monthly_spending") }}', '')
                as double
            ),
            last_12.avg_spending
        ) as fi_monthly_spending,
        {{ var('fi_withdrawal_rate') }} as fi_withdrawal_rate,
        {{ var('fi_real_return') }} as fi_real_return,
        pow(1 + {{ var('fi_real_return') }}, 1 / 12) - 1 as monthly_return
    from latest
    cross join last_12

),

targets as (

    select
        *,
        fi_monthly_spending * 12 / fi_withdrawal_rate as fi_target_value,
        date_diff('month', projection_from, fi_target_month) as months_to_target
    from params

),

projected as (

    select
        *,
        -- the monthly new money that takes today's value to the target by
        -- the target month (future value of the value plus an annuity)
        case
            when months_to_target > 0
                then
                    (fi_target_value - total_value * pow(1 + monthly_return, months_to_target))
                    * monthly_return
                    / (pow(1 + monthly_return, months_to_target) - 1)
        end as required_monthly_new_money,
        -- months for the current pace to reach the target, the same equation
        -- solved for the months; NULL when it never does
        case
            when total_value >= fi_target_value then 0
            when total_value * monthly_return + avg_new_money > 0
                then ceil(
                    ln(
                        (fi_target_value * monthly_return + avg_new_money)
                        / (total_value * monthly_return + avg_new_money)
                    )
                    / ln(1 + monthly_return)
                )
        end as months_at_current_pace
    from targets

)

select
    reference_date as as_of_date,
    projection_from,
    total_value as wealth,
    fi_monthly_spending,
    fi_withdrawal_rate,
    fi_real_return,
    monthly_return,
    fi_target_value,
    total_value / fi_target_value as fi_progress,
    fi_target_month,
    months_to_target,
    greatest(required_monthly_new_money, 0) as required_monthly_new_money,
    avg_new_money as current_monthly_new_money,
    -- a century is as good as never
    case
        when months_at_current_pace <= 1200
            then cast(
                projection_from + to_months(cast(months_at_current_pace as integer)) as date
            )
    end as projected_fi_month,
    {{ new_money_goal(
        "cast(date_trunc('month', " ~ as_of_date() ~ ") as date)",
        'greatest(required_monthly_new_money, 0)'
    ) }} as new_money_goal,
    liquid_reserve as reserve,
    {{ var('reserve_min_months') }} * avg_monthly_spending as reserve_target,
    liquid_reserve / nullif({{ var('reserve_min_months') }} * avg_monthly_spending, 0)
        as reserve_progress
from projected
