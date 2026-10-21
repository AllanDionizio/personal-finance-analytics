-- One row per closed budget month: the cash-flow metrics the dashboard
-- reads, defined once here so every page adds them up the same way.
--
-- A month is closed when it comes before the as-of month (the newest month
-- with a settled transaction): the as-of month is still being paid, so its
-- totals would understate both income and spending.
--
-- income is operating income only: money from selling an asset is real
-- cash in but not earned, so it is kept apart as non_operating_income (the
-- category's is_operating flag, from seed income_groups).
--
-- savings = income - spending, i.e. what went into investments plus what
-- stayed in the account. Investment contributions are not spending.
--
-- new_money is what the household added to its wealth from outside the
-- portfolio: every contribution when the investment rows are all new money,
-- or, when they also book reinvested redemptions (var new_money_source),
-- savings plus asset sales minus dividends, which the portfolio earned.

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
        facts.is_dividend,
        categories.macro_category,
        coalesce(categories.is_operating, true) as is_operating
    from {{ ref('fct_transactions') }} as facts
    left join {{ ref('dim_category') }} as categories
        on facts.category_key = categories.category_key
    cross join as_of
    where facts.budget_month < as_of.as_of_month

),

monthly as (

    select
        budget_month,
        sum(effective_amount) filter (where side = 'credit' and is_operating) as income,
        sum(effective_amount) filter (
            where side = 'credit' and not is_operating
        ) as non_operating_income,
        sum(effective_amount) filter (where is_dividend) as dividends,
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
        -- Every contribution, whatever its OK column says: the sheets leave
        -- them at 'Não' so the workbook's own report doesn't count them as
        -- spending.
        sum(amount) filter (where is_investment_contribution) as invested
    from transactions
    group by budget_month

)

select
    budget_month,
    coalesce(income, 0) as income,
    coalesce(non_operating_income, 0) as non_operating_income,
    coalesce(dividends, 0) as dividends,
    coalesce(spending, 0) as spending,
    coalesce(fixed_spending, 0) as fixed_spending,
    coalesce(variable_spending, 0) as variable_spending,
    coalesce(unclassified_spending, 0) as unclassified_spending,
    coalesce(invested, 0) as invested,
    coalesce(income, 0) - coalesce(spending, 0) as savings,
    case
        when '{{ var("new_money_source") }}' = 'savings'
            then
                coalesce(income, 0) - coalesce(spending, 0)
                + coalesce(non_operating_income, 0) - coalesce(dividends, 0)
        else coalesce(invested, 0)
    end as new_money
from monthly
