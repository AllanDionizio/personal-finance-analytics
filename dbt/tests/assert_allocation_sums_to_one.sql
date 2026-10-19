-- In every snapshot that reports allocations, they add up to 100%
-- (within rounding).

select
    reference_date,
    sum(allocation_pct) as total_allocation
from {{ ref('fct_portfolio_snapshots') }}
group by reference_date
having
    count(allocation_pct) = count(*)
    and abs(sum(allocation_pct) - 1) > 0.001
