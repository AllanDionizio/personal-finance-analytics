-- Every raw transaction reaches the fact, with its amount unchanged: per
-- source file, the row counts and amount totals match.

with

raw_totals as (

    select
        source_file,
        count(*) as n_rows,
        sum(amount) as total_amount
    from {{ source('raw', 'transactions') }}
    group by source_file

),

fact_totals as (

    select
        source_file,
        count(*) as n_rows,
        sum(amount) as total_amount
    from {{ ref('fct_transactions') }}
    group by source_file

)

select
    coalesce(raw_totals.source_file, fact_totals.source_file) as source_file,
    raw_totals.n_rows as raw_rows,
    fact_totals.n_rows as fact_rows,
    raw_totals.total_amount as raw_amount,
    fact_totals.total_amount as fact_amount
from raw_totals
full outer join fact_totals
    on raw_totals.source_file = fact_totals.source_file
where
    raw_totals.n_rows is distinct from fact_totals.n_rows
    or raw_totals.total_amount is distinct from fact_totals.total_amount
