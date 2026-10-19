-- Per reference date, the fact's portfolio total equals the raw total of the
-- newest file that holds that snapshot: deduplication drops whole copies,
-- never single holdings.

with

raw_snapshots as (

    select
        reference_date,
        source_file,
        sum(gross_value) as total_value
    from {{ source('raw', 'portfolio_snapshots') }}
    group by reference_date, source_file

),

newest_raw as (

    select
        reference_date,
        total_value
    from raw_snapshots
    -- Newest by the year in the file name, as stg_portfolio_snapshots does
    qualify
        row_number() over (
            partition by reference_date
            order by cast(regexp_extract(source_file, '(20\d{2})', 1) as integer) desc
        ) = 1

),

fact as (

    select
        reference_date,
        sum(gross_value) as total_value
    from {{ ref('fct_portfolio_snapshots') }}
    group by reference_date

)

select
    coalesce(newest_raw.reference_date, fact.reference_date) as reference_date,
    newest_raw.total_value as raw_value,
    fact.total_value as fact_value
from newest_raw
full outer join fact
    on newest_raw.reference_date = fact.reference_date
where newest_raw.total_value is distinct from fact.total_value
