-- One row per holding per reference date. "Situação Atual" is cumulative, so
-- the same snapshot appears in several yearly files; only the newest file's
-- copy is kept, which also picks up later corrections (data-model 6.8).

with

source as (

    select
        *,
        cast(regexp_extract(source_file, '(20\d{2})', 1) as integer) as file_year,
        trim(bank) as trimmed_bank,
        trim(asset) as trimmed_asset
    from {{ source('raw', 'portfolio_snapshots') }}

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

)

select
    {{ dbt_utils.generate_surrogate_key([
        'newest_file.reference_date',
        'canonical_banks.bank',
        'newest_file.trimmed_asset',
    ]) }} as snapshot_id,
    newest_file.reference_date,
    canonical_banks.bank,
    newest_file.trimmed_asset as asset,
    case
        when newest_file.trimmed_asset ilike 'FII%' then 'Real estate fund'
        when newest_file.trimmed_asset ilike '%bitcoin%' then 'Crypto'
        when newest_file.trimmed_asset ilike 'Saldo%' then 'Cash'
        when
            newest_file.trimmed_asset ilike '%multimercado%'
            or newest_file.trimmed_asset ilike '%long short%'
            then 'Multimarket fund'
        when
            regexp_matches(
                newest_file.trimmed_asset,
                '^(CDB|LCI|LCA|CRI|CRA|CCB|Tesouro|Recebíveis|Fundo Renda Fixa)'
            )
            or newest_file.trimmed_asset ilike '%CDI%'
            then 'Fixed income'
        else 'Other'
    end as asset_class,
    newest_file.gross_value,
    newest_file.allocation_pct,
    newest_file.maturity_date,
    newest_file.mom,
    newest_file.yoy,
    newest_file.net_value_at_maturity,
    newest_file.return_to_date,
    newest_file.return_at_maturity,
    newest_file.source_file,
    newest_file.source_block_row,
    newest_file.extracted_at
from newest_file
inner join canonical_banks
    on lower(newest_file.trimmed_bank) = canonical_banks.bank_key
