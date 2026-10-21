-- One row per asset per reference date: the investment portfolio's history.
--
-- A holding has daily liquidity when it can be withdrawn the same day
-- without losing what was put in: the cash balance, fixed income with no
-- maturity date, a name that says so ("Liq. Diária"), or a name matched by
-- var liquid_assets. That var is a JSON list of {"match": ilike pattern,
-- "note": text}, in the order to withdraw from; the household's own products
-- live in .env.real. The liquid holdings make up the reserve (fct_net_worth),
-- withdrawn from the cash balance first, then the listed order, then the
-- largest; an empty one gets no place in that order.

{%- set liquid_assets = fromjson(var('liquid_assets')) %}

with

snapshots as (

    select * from {{ ref('stg_portfolio_snapshots') }}

),

listed as (

    select
        *,
        {% if liquid_assets -%}
            case
                {%- for item in liquid_assets %}
                    when asset ilike '{{ item.match | replace("'", "''") }}' then {{ loop.index }}
                {%- endfor %}
            end
        {%- else -%}
            cast(null as integer)
        {%- endif %} as listed_order,
        {% if liquid_assets -%}
            case
                {%- for item in liquid_assets %}
                    when asset ilike '{{ item.match | replace("'", "''") }}'
                        then {{ "'" ~ (item.note | default('') | replace("'", "''")) ~ "'" }}
                {%- endfor %}
            end
        {%- else -%}
            cast(null as varchar)
        {%- endif %} as listed_note
    from snapshots

),

flagged as (

    select
        *,
        asset_class = 'Cash'
        or (asset_class = 'Fixed income' and maturity_date is null)
        or regexp_matches(asset, '(?i)liq\.?\s*di[aá]ria')
        or listed_order is not null as is_liquid
    from listed

)

select
    snapshot_id,
    reference_date,
    bank,
    asset,
    asset_class,
    gross_value,
    allocation_pct,
    maturity_date,
    mom,
    yoy,
    net_value_at_maturity,
    return_to_date,
    return_at_maturity,
    is_liquid,
    -- an empty holding has nothing to withdraw
    case
        when is_liquid and gross_value > 0
            then row_number() over (
                partition by reference_date, is_liquid and gross_value > 0
                order by asset_class = 'Cash' desc, listed_order nulls last, gross_value desc
            )
    end as withdrawal_order,
    nullif(listed_note, '') as liquidity_note
from flagged
