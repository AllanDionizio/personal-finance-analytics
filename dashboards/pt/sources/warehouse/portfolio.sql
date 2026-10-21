-- The English source (dashboards/sources/warehouse/portfolio.sql) with the
-- asset classes in Portuguese.
select
    snapshot_id,
    reference_date,
    bank,
    asset,
    case asset_class
        when 'Fixed income' then 'Renda fixa'
        when 'Multimarket fund' then 'Multimercado'
        when 'Real estate fund' then 'FII'
        when 'Crypto' then 'Cripto'
        when 'Cash' then 'Saldo em conta'
        when 'Other' then 'Outros'
        else asset_class
    end as asset_class,
    gross_value,
    allocation_pct,
    maturity_date
from marts.fct_portfolio_snapshots
