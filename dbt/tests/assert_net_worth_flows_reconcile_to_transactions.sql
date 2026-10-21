-- Every contribution (whatever its status) and every settled dividend
-- between the first and the last snapshot lands in exactly one period of
-- fct_net_worth: the windows neither overlap nor leave gaps.

with

bounds as (

    select
        min(reference_date) as first_date,
        max(reference_date) as last_date
    from {{ ref('fct_net_worth') }}

),

transactions as (

    select
        sum(amount) filter (where is_investment_contribution) as contributions,
        sum(amount) filter (where is_dividend and is_settled) as dividends
    from {{ ref('fct_transactions') }}
    cross join bounds
    where
        coalesce(transaction_date, budget_month + 14) > bounds.first_date
        and coalesce(transaction_date, budget_month + 14) <= bounds.last_date

),

periods as (

    select
        sum(contributions) as contributions,
        sum(dividends) as dividends
    from {{ ref('fct_net_worth') }}

)

select *
from transactions
cross join periods
where
    transactions.contributions is distinct from periods.contributions
    or transactions.dividends is distinct from periods.dividends
