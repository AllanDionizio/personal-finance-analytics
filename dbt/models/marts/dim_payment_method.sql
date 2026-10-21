-- How a debit was paid: one of the cards (by cell color) or anything else.

with

colors as (

    select * from {{ ref('color_mapping') }}
    where dimension = 'payment_method'

),

payment_methods as (

    select
        value as payment_method,
        'credit_card' as method_type,
        '#' || hex as source_color
    from colors

    union all

    select
        'Other' as payment_method,
        'other' as method_type,
        null as source_color

)

select
    {{ dbt_utils.generate_surrogate_key(['payment_method']) }} as payment_method_key,
    payment_method,
    {{ display_name('payment_method') }} as display_name,
    method_type,
    source_color
from payment_methods
