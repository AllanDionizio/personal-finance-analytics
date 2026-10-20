-- Every settled transaction of a closed month reaches the cash flow: per
-- side, the mart's totals match fct_transactions over the same months.

with

closed_transactions as (

    select
        sum(effective_amount) filter (where side = 'credit') as income,
        sum(effective_amount) filter (where side = 'debit') as spending
    from {{ ref('fct_transactions') }}
    where budget_month <= (select max(budget_month) from {{ ref('fct_monthly_cashflow') }})

),

cashflow as (

    select
        sum(income) as income,
        sum(spending) as spending
    from {{ ref('fct_monthly_cashflow') }}

)

select *
from closed_transactions
cross join cashflow
where
    closed_transactions.income is distinct from cashflow.income
    or closed_transactions.spending is distinct from cashflow.spending
