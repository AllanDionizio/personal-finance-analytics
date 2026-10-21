-- Every flow between the first and the last snapshot lands in exactly one
-- period of fct_net_worth: the windows neither overlap nor leave gaps. The
-- flows are every contribution (whatever its status) and every settled
-- dividend, or, when new money comes from savings, each closed month's
-- new_money and dividends up to the last complete period.

with

{% if var('new_money_source') == 'savings' -%}

bounds as (

    select
        min(reference_date) as first_date,
        max(reference_date) filter (where contributions is not null) as last_date
    from {{ ref('fct_net_worth') }}

),

transactions as (

    select
        sum(new_money) as contributions,
        sum(dividends) as dividends
    from {{ ref('fct_monthly_cashflow') }}
    cross join bounds
    where
        budget_month + 14 > bounds.first_date
        and budget_month + 14 <= bounds.last_date

),

{%- else -%}

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

{%- endif %}

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
