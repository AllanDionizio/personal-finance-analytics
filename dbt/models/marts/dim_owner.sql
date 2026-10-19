-- Who earned a credit, as encoded by the amount cell's color.

with

colors as (

    select * from {{ ref('color_mapping') }}
    where dimension = 'owner'

),

owners as (

    select
        value as owner,
        '#' || hex as source_color
    from colors

    union all

    select
        'Other' as owner,
        null as source_color

)

select
    {{ dbt_utils.generate_surrogate_key(['owner']) }} as owner_key,
    owner,
    source_color
from owners
