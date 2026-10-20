-- One row per portfolio snapshot: the portfolio's value, the money that came
-- in from outside since the previous snapshot, the return that leaves, and
-- inflation over the same periods, so "did we beat inflation?" compares like
-- with like.
--
-- External flows are the recorded investment contributions only. In the
-- workbooks a maturing asset is reinvested inside the portfolio and books
-- nothing; a withdrawal to spend isn't recorded either, which understates
-- that period's return (it never overstates it). Dividends are paid into the
-- account, so they count as return on top of the change in value.
--
-- period_return is the modified Dietz return: the gain over the average
-- capital, with contributions counted for half the period. Returns and
-- inflation are then chained over the last 12 periods and over the year.
--
-- The liquid reserve is the cash balance plus fixed income with no maturity
-- date (daily liquidity), measured in months of fixed spending against the
-- target band in the project vars reserve_min_months / reserve_max_months.

with

snapshots as (

    select
        reference_date,
        sum(gross_value) as total_value,
        coalesce(sum(gross_value) filter (
            where asset_class = 'Cash'
            or (asset_class = 'Fixed income' and maturity_date is null)
        ), 0) as liquid_reserve
    from {{ ref('fct_portfolio_snapshots') }}
    group by reference_date

),

periods as (

    select
        *,
        lag(reference_date) over (order by reference_date) as previous_date,
        lag(total_value) over (order by reference_date) as previous_value
    from snapshots

),

flows as (

    -- A flow without a date counts at mid-month of its budget month.
    select
        periods.reference_date,
        coalesce(sum(facts.amount) filter (
            where facts.is_investment_contribution
        ), 0) as contributions,
        coalesce(sum(facts.amount) filter (
            where facts.is_dividend
        ), 0) as dividends
    from periods
    left join {{ ref('fct_transactions') }} as facts
        on
            facts.is_settled
            and (facts.is_investment_contribution or facts.is_dividend)
            and coalesce(
                facts.transaction_date, facts.budget_month + 14
            ) > periods.previous_date
            and coalesce(
                facts.transaction_date, facts.budget_month + 14
            ) <= periods.reference_date
    group by periods.reference_date

),

inflation as (

    -- IPCA of every month after the previous snapshot's month, up to this
    -- snapshot's month; NULL while one of those months isn't published.
    select
        periods.reference_date,
        date_diff(
            'month',
            date_trunc('month', periods.previous_date),
            date_trunc('month', periods.reference_date)
        ) as months_expected,
        count(ipca.month) as months_found,
        exp(sum(ln(1 + ipca.ipca_rate))) - 1 as compounded
    from periods
    left join {{ ref('fct_inflation_monthly') }} as ipca
        on
            ipca.month > date_trunc('month', periods.previous_date)
            and ipca.month <= date_trunc('month', periods.reference_date)
    where periods.previous_date is not null
    group by periods.reference_date, periods.previous_date

),

spending as (

    -- The 12 closed months up to the snapshot's month.
    select
        periods.reference_date,
        count(*) as months,
        avg(cashflow.spending) as avg_monthly_spending,
        avg(cashflow.fixed_spending) as avg_monthly_fixed_spending
    from periods
    inner join {{ ref('fct_monthly_cashflow') }} as cashflow
        on
            cashflow.budget_month <= date_trunc('month', periods.reference_date)
            and cashflow.budget_month
            > date_trunc('month', periods.reference_date) - interval 12 month
    group by periods.reference_date

),

returns as (

    select
        periods.reference_date,
        periods.total_value,
        periods.liquid_reserve,
        periods.previous_value,
        case when periods.previous_date is not null then flows.contributions end
            as contributions,
        case when periods.previous_date is not null then flows.dividends end as dividends,
        periods.total_value - periods.previous_value - flows.contributions + flows.dividends
            as period_gain,
        (periods.total_value - periods.previous_value - flows.contributions + flows.dividends)
        / nullif(periods.previous_value + 0.5 * flows.contributions, 0) as period_return,
        case
            when inflation.months_expected = 0 then 0
            when inflation.months_found = inflation.months_expected then inflation.compounded
        end as period_inflation,
        case when spending.months = 12 then spending.avg_monthly_spending end
            as avg_monthly_spending,
        case when spending.months = 12 then spending.avg_monthly_fixed_spending end
            as avg_monthly_fixed_spending
    from periods
    inner join flows on periods.reference_date = flows.reference_date
    left join inflation on periods.reference_date = inflation.reference_date
    left join spending on periods.reference_date = spending.reference_date

),

chained as (

    select
        *,
        exp(sum(ln(1 + period_return)) over last_12) - 1 as return_12m_raw,
        exp(sum(ln(1 + period_inflation)) over last_12) - 1 as inflation_12m_raw,
        count(period_return) over last_12 as returns_in_12m,
        count(period_inflation) over last_12 as inflations_in_12m,
        exp(sum(ln(1 + period_return)) over this_year) - 1 as return_ytd_raw,
        exp(sum(ln(1 + period_inflation)) over this_year) - 1 as inflation_ytd_raw,
        count(period_return) over this_year as returns_in_year,
        count(period_inflation) over this_year as inflations_in_year
    from returns
    window
        last_12 as (order by reference_date rows between 11 preceding and current row),
        this_year as (
            partition by year(reference_date)
            order by reference_date
            rows between unbounded preceding and current row
        )

),

compared as (

    select
        *,
        -- a full year of periods, with inflation known for each of them
        case
            when returns_in_12m = 12 and inflations_in_12m = 12 then return_12m_raw
        end as return_12m,
        case
            when returns_in_12m = 12 and inflations_in_12m = 12 then inflation_12m_raw
        end as inflation_12m,
        case
            when returns_in_year > 0 and inflations_in_year = returns_in_year then return_ytd_raw
        end as return_ytd,
        case
            when returns_in_year > 0 and inflations_in_year = returns_in_year
                then inflation_ytd_raw
        end as inflation_ytd
    from chained

)

select
    reference_date,
    total_value,
    liquid_reserve,
    contributions,
    dividends,
    period_gain,
    period_return,
    period_inflation,
    return_12m,
    inflation_12m,
    (1 + return_12m) / (1 + inflation_12m) - 1 as real_return_12m,
    return_ytd,
    inflation_ytd,
    (1 + return_ytd) / (1 + inflation_ytd) - 1 as real_return_ytd,
    avg_monthly_spending,
    avg_monthly_fixed_spending,
    total_value / nullif(avg_monthly_spending, 0) as runway_months,
    liquid_reserve / nullif(avg_monthly_fixed_spending, 0) as reserve_months,
    case
        when avg_monthly_fixed_spending is null then null
        when
            liquid_reserve / nullif(avg_monthly_fixed_spending, 0)
            < {{ var('reserve_min_months') }} then 'Below target'
        when
            liquid_reserve / nullif(avg_monthly_fixed_spending, 0)
            > {{ var('reserve_max_months') }} then 'Above target'
        else 'Within target'
    end as reserve_status
from compared
