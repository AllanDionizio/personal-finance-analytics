-- One row per transaction: typed, colors resolved to owner / payment method,
-- installment tag parsed, flags for the categories that drive logic.
-- Rules: docs/data-model.md, sections 3 and 6.

with

source as (

    select * from {{ source('raw', 'transactions') }}

),

themes as (

    select * from {{ source('raw', 'workbook_themes') }}

),

colors as (

    select * from {{ ref('color_mapping') }}

),

categories as (

    select * from {{ ref('stg_categories') }}

),

parsed as (

    select
        source.*,
        cast(regexp_extract(source.source_file, '(20\d{2})', 1) as integer) as file_year,
        list_position(
            ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'],
            lower(left(trim(source.source_sheet), 3))
        ) as sheet_month,
        nullif(regexp_extract(source.description, '\((\d+)\s*/\s*(\d+)\)', 1), '')
            as tag_number,
        nullif(regexp_extract(source.description, '\((\d+)\s*/\s*(\d+)\)', 2), '')
            as tag_count,
        {{ resolve_color_hex(
            'source.description_color_type',
            'source.description_color_value',
            'description_theme.hex'
        ) }} as description_hex,
        {{ resolve_color_hex(
            'source.amount_color_type',
            'source.amount_color_value',
            'amount_theme.hex'
        ) }} as amount_hex
    from source
    left join themes as description_theme
        on
            source.description_color_type = 'theme'
            and source.source_file = description_theme.source_file
            and try_cast(source.description_color_value as integer)
            = description_theme.theme_index
    left join themes as amount_theme
        on
            source.amount_color_type = 'theme'
            and source.source_file = amount_theme.source_file
            and try_cast(source.amount_color_value as integer) = amount_theme.theme_index

),

colored as (

    select
        parsed.*,
        owner_color.value as amount_owner,
        amount_card.value as amount_card,
        description_card.value as description_card
    from parsed
    left join colors as owner_color
        on parsed.amount_hex = owner_color.hex and owner_color.dimension = 'owner'
    left join colors as amount_card
        on parsed.amount_hex = amount_card.hex and amount_card.dimension = 'payment_method'
    left join colors as description_card
        on
            parsed.description_hex = description_card.hex
            and description_card.dimension = 'payment_method'

),

typed as (

    select
        transaction_id,
        transaction_date,
        make_date(file_year, sheet_month, 1) as budget_month,
        side,
        case side when 'credit' then 'income' else 'expense' end as category_type,
        {{ clean_description('description') }} as description,
        description as raw_description,
        trim(category) as category,
        nullif(trim(macro_category), '') as raw_macro_category,
        amount,
        -- 2021 workbooks don't color credits by owner (data-model 6.2).
        case
            when side = 'debit' then null
            when file_year = 2021 then 'Person A'
            else coalesce(amount_owner, 'Other')
        end as owner,
        -- A known card on the amount cell wins; the description cell is the
        -- fallback. Any other color, such as a manual highlight, is 'Other'.
        case
            when side = 'credit' then null
            else coalesce(amount_card, description_card, 'Other')
        end as payment_method,
        coalesce(lower(trim(status)) = 'sim', false) as is_settled,
        coalesce(cast(tag_number as integer), 1) as installment_number,
        coalesce(cast(tag_count as integer), 1) as installment_count,
        source_file,
        source_sheet,
        source_row,
        extracted_at
    from colored

)

select
    typed.transaction_id,
    typed.transaction_date,
    typed.budget_month,
    typed.side,
    typed.description,
    typed.raw_description,
    categories.category_key,
    typed.category,
    -- Debits only: typed in the sheet since 2022; otherwise from the
    -- category list, and 'Unknown' when the category isn't in it.
    case
        when typed.side = 'credit' then null
        else coalesce(
            {{ translate_macro_category('typed.raw_macro_category') }},
            categories.macro_category,
            'Unknown'
        )
    end as macro_category,
    typed.amount,
    typed.owner,
    typed.payment_method,
    typed.is_settled,
    typed.is_settled
    and not (typed.side = 'debit' and typed.category = 'Investimento') as is_effective,
    typed.side = 'credit' and typed.category = 'Proventos' as is_dividend,
    typed.side = 'debit' and typed.category = 'Investimento' as is_investment_contribution,
    typed.side = 'debit' and typed.category = 'Cartão de Crédito' as is_card_adjustment,
    typed.installment_number,
    typed.installment_count,
    typed.installment_count > 1 as is_installment,
    typed.source_file,
    typed.source_sheet,
    typed.source_row,
    typed.extracted_at
from typed
left join categories
    on
        typed.category_type = categories.category_type
        and typed.category = categories.category
