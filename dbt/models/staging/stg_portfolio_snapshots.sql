-- One row per holding per reference date. "Situação Atual" is cumulative, so
-- the same snapshot appears in several yearly files; only the newest file's
-- copy is kept, which also picks up later corrections (data-model 6.8).
-- The bank join is a left join so a blank bank fails not_null instead of
-- dropping the row.

with

source as (

    select
        *,
        cast(regexp_extract(source_file, '(20\d{2})', 1) as integer) as file_year,
        trim(bank) as trimmed_bank,
        trim(asset) as trimmed_asset
    from {{ source('raw', 'portfolio_snapshots') }}

),

aliases as (

    select * from {{ ref('asset_aliases') }}

),

newest_file as (

    select *
    from source
    qualify file_year = max(file_year) over (partition by reference_date)

),

-- Bank names drift in case when typed by hand ("Banco alfa (fundos)").
-- Every spelling of a bank maps to its most frequent one.
bank_spellings as (

    select
        lower(trimmed_bank) as bank_key,
        trimmed_bank as bank,
        count(*) as n_rows
    from source
    group by all

),

canonical_banks as (

    select
        bank_key,
        bank
    from bank_spellings
    qualify row_number() over (partition by bank_key order by n_rows desc, bank asc) = 1

),

-- Notes typed over an asset name map back to the asset (seed asset_aliases),
-- so its history stays one series.
cleaned as (

    select
        newest_file.*,
        canonical_banks.bank as clean_bank,
        coalesce(aliases.asset, newest_file.trimmed_asset) as clean_asset
    from newest_file
    left join canonical_banks
        on lower(newest_file.trimmed_bank) = canonical_banks.bank_key
    left join aliases
        on
            canonical_banks.bank = aliases.bank
            and newest_file.trimmed_asset = aliases.raw_asset

)

select
    {{ dbt_utils.generate_surrogate_key(['reference_date', 'clean_bank', 'clean_asset']) }}
        as snapshot_id,
    reference_date,
    clean_bank as bank,
    clean_asset as asset,
    trimmed_asset as raw_asset,
    case
        when clean_asset ilike 'FII%' then 'Real estate fund'
        when clean_asset ilike '%bitcoin%' then 'Crypto'
        when clean_asset ilike 'Saldo%' then 'Cash'
        when
            clean_asset ilike '%multimercado%'
            or clean_asset ilike '%long short%'
            then 'Multimarket fund'
        when
            regexp_matches(
                clean_asset,
                '^(CDB|LCI|LCA|CRI|CRA|CCB|Tesouro|Recebíveis|Fundo Renda Fixa)'
            )
            or clean_asset ilike '%CDI%'
            then 'Fixed income'
        else 'Other'
    end as asset_class,
    gross_value,
    allocation_pct,
    maturity_date,
    mom,
    yoy,
    net_value_at_maturity,
    return_to_date,
    return_at_maturity,
    source_file,
    source_block_row,
    extracted_at
from cleaned
