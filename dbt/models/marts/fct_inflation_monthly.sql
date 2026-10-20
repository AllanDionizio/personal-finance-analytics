-- One row per month of official inflation (IPCA), with the price index and
-- the 12-month and year-to-date rates built from the monthly changes.

with

monthly as (

    select
        month,
        ipca_pct,
        ipca_pct / 100 as ipca_rate
    from {{ ref('ipca_monthly') }}

),

compounded as (

    select
        *,
        -- product of (1 + rate) as exp(sum(ln)), over growing or fixed windows
        exp(sum(ln(1 + ipca_rate)) over (order by month)) as growth_since_start,
        exp(sum(ln(1 + ipca_rate)) over (
            order by month rows between 11 preceding and current row
        )) - 1 as ipca_12m_raw,
        count(*) over (
            order by month rows between 11 preceding and current row
        ) as months_in_window,
        exp(sum(ln(1 + ipca_rate)) over (
            partition by year(month) order by month
        )) - 1 as ipca_ytd
    from monthly

)

select
    month,
    ipca_pct,
    ipca_rate,
    -- 100 at the month before the series starts
    100 * growth_since_start as price_index,
    case when months_in_window = 12 then ipca_12m_raw end as ipca_12m,
    ipca_ytd
from compounded
