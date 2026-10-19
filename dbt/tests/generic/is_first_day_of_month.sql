-- Fails on every row whose date is not the first day of its month, as
-- budget_month must be: facts join the calendar on it.
{% test is_first_day_of_month(model, column_name) %}

    select {{ column_name }}
    from {{ model }}
    where {{ column_name }} is not null
      and {{ column_name }} <> date_trunc('month', {{ column_name }})

{% endtest %}
