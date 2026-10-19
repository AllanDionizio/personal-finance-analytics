-- One row per asset per reference date: the investment portfolio's history.

select
    snapshot_id,
    reference_date,
    bank,
    asset,
    asset_class,
    gross_value,
    allocation_pct,
    maturity_date,
    mom,
    yoy,
    net_value_at_maturity,
    return_to_date,
    return_at_maturity
from {{ ref('stg_portfolio_snapshots') }}
