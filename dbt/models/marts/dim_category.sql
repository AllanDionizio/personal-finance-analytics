-- One row per category and type, plus an 'Unknown' member for transactions
-- whose category is in no list, so the fact's key is never NULL. Income
-- categories carry their source group and whether they are operating income
-- (seed income_groups); one missing from the seed counts as 'Other'.

with

categories as (

    select * from {{ ref('stg_categories') }}

),

income_groups as (

    select * from {{ ref('income_groups') }}

)

select
    categories.category_key,
    categories.category_type,
    categories.category,
    categories.macro_category,
    categories.is_legacy,
    case
        when categories.category_type = 'income'
            then coalesce(income_groups.income_group, 'Other')
    end as income_group,
    case
        when categories.category_type = 'income'
            then coalesce(income_groups.is_operating, true)
    end as is_operating
from categories
left join income_groups
    on categories.category = income_groups.category

union all

select
    'unknown' as category_key,
    null as category_type,
    'Unknown' as category,
    'Unknown' as macro_category,
    false as is_legacy,
    null as income_group,
    null as is_operating
