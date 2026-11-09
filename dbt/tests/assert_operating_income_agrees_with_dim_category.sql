-- Operating income read straight from dim_category.is_operating, the way the
-- Income page filters it, adds up to the income in fct_monthly_cashflow over
-- the same closed months. Fails if the two rules drift apart again (as they
-- did for the 'Unknown' category, whose is_operating was NULL).

with

by_dimension as (

    select sum(facts.effective_amount) as income
    from {{ ref('fct_transactions') }} as facts
    left join {{ ref('dim_category') }} as categories
        on facts.category_key = categories.category_key
    where
        facts.side = 'credit'
        and categories.is_operating
        and facts.budget_month <= (select max(budget_month) from {{ ref('fct_monthly_cashflow') }})

),

cashflow as (

    select sum(income) as income
    from {{ ref('fct_monthly_cashflow') }}

)

select *
from by_dimension
cross join cashflow
where by_dimension.income is distinct from cashflow.income
