-- One row per category and type, plus an 'Unknown' member for transactions
-- whose category is in no list, so the fact's key is never NULL. Income
-- categories carry their source group and whether they are operating income
-- (seed income_groups); one missing from the seed counts as 'Other'.
-- The 'Unknown' member gets the same defaults ('Other', operating), so a
-- credit typed with an unlisted category counts as income the same way in
-- fct_monthly_cashflow and in anything that filters on is_operating.

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
    'Other' as income_group,
    true as is_operating
