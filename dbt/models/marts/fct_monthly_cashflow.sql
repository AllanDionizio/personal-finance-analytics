-- One row per closed budget month: the cash-flow metrics the dashboard
-- reads, defined once here so every page adds them up the same way.
--
-- A month is closed when it comes before the as-of month (the newest month
-- with a settled transaction): the as-of month is still being paid, so its
-- totals would understate both income and spending.
--
-- savings = income - spending, i.e. what went into investments plus what
-- stayed in the account. Investment contributions are not spending.

with

as_of as (

    {{ as_of_month() }}

),

transactions as (

    select
        facts.budget_month,
        facts.side,
        facts.amount,
        facts.effective_amount,
        facts.is_settled,
        facts.is_investment_contribution,
        categories.macro_category
    from {{ ref('fct_transactions') }} as facts
    left join {{ ref('dim_category') }} as categories
        on facts.category_key = categories.category_key
    cross join as_of
    where facts.budget_month < as_of.as_of_month

),

monthly as (

    select
        budget_month,
        sum(effective_amount) filter (where side = 'credit') as income,
        sum(effective_amount) filter (where side = 'debit') as spending,
        sum(effective_amount) filter (
            where side = 'debit' and macro_category = 'Fixed'
        ) as fixed_spending,
        sum(effective_amount) filter (
            where side = 'debit' and macro_category = 'Variable'
        ) as variable_spending,
        sum(effective_amount) filter (
            where side = 'debit' and coalesce(macro_category, '') not in ('Fixed', 'Variable')
        ) as unclassified_spending,
        sum(amount) filter (
            where is_investment_contribution and is_settled
        ) as invested
    from transactions
    group by budget_month

)

select
    budget_month,
    coalesce(income, 0) as income,
    coalesce(spending, 0) as spending,
    coalesce(fixed_spending, 0) as fixed_spending,
    coalesce(variable_spending, 0) as variable_spending,
    coalesce(unclassified_spending, 0) as unclassified_spending,
    coalesce(invested, 0) as invested,
    coalesce(income, 0) - coalesce(spending, 0) as savings
from monthly
