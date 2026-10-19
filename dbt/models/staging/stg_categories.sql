-- Canonical categories plus the legacy ones that only appear in old files.
-- A legacy name that made it back into the canonical list keeps the
-- canonical macro-category.

with

canonical as (

    select
        category_type,
        trim(category) as category,
        trim(macro_category) as macro_category
    from {{ source('raw', 'category_config') }}

),

legacy as (

    select
        category_type,
        trim(category) as category,
        trim(macro_category) as macro_category
    from {{ ref('legacy_categories') }}

),

unioned as (

    select
        *,
        false as is_legacy
    from canonical

    union all

    select
        legacy.*,
        true as is_legacy
    from legacy
    anti join canonical
        on
            legacy.category_type = canonical.category_type
            and legacy.category = canonical.category

)

select
    {{ dbt_utils.generate_surrogate_key(['category_type', 'category']) }} as category_key,
    category_type,
    category,
    {{ translate_macro_category('macro_category') }} as macro_category,
    is_legacy
from unioned
