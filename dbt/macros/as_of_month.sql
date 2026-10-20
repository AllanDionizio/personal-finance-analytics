-- The as-of month: the newest budget month with a settled transaction.
-- Months before it are closed; the as-of month itself is still being paid.
-- Used as a one-row CTE wherever a model needs that cut.
{% macro as_of_month() -%}
    select max(budget_month) as as_of_month
    from {{ ref('stg_transactions') }}
    where is_settled
{%- endmacro %}
