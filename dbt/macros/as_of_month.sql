-- The as-of month: the newest budget month with a settled transaction, but
-- never past the current month. The sheets also mark future rows as settled
-- (a card installment already on the bill, a planned 13th salary), and those
-- must not close months that haven't happened. Months before it are closed;
-- the as-of month itself is still being paid. Used as a one-row CTE wherever
-- a model needs that cut. Var `as_of_date` pins "today" (unit tests, reruns).
{% macro as_of_month() -%}
    select
        least(
            max(budget_month),
            cast(date_trunc('month', {{ as_of_date() }}) as date)
        ) as as_of_month
    from {{ ref('stg_transactions') }}
    where is_settled
{%- endmacro %}

{% macro as_of_date() -%}
    {%- if var('as_of_date', none) -%}
        date '{{ var("as_of_date") }}'
    {%- else -%}
        current_date
    {%- endif -%}
{%- endmacro %}
