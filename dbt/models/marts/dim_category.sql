-- One row per category and type, plus an 'Unknown' member for transactions
-- whose category is in no list, so the fact's key is never NULL.

with

categories as (

    select * from {{ ref('stg_categories') }}

)

select
    category_key,
    category_type,
    category,
    macro_category,
    is_legacy
from categories

union all

select
    'unknown' as category_key,
    null as category_type,
    'Unknown' as category,
    'Unknown' as macro_category,
    false as is_legacy
