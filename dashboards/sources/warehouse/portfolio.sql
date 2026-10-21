-- One row per asset per reference date of the investment portfolio.
select
    snapshot_id,
    reference_date,
    bank,
    asset,
    asset_class,
    gross_value,
    allocation_pct,
    maturity_date,
    is_liquid,
    withdrawal_order,
    liquidity_note
from marts.fct_portfolio_snapshots
