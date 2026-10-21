{% macro new_money_goal(month, cap) -%}
    {#- The new money goal of a month: none before new_money_goal_from, then the
        starting goal raised by one step every 12 months, never above cap. -#}
    case
        when {{ month }} >= date '{{ var("new_money_goal_from") }}'
            then least(
                {{ var('new_money_goal_start') }}
                + {{ var('new_money_goal_step') }} * floor(
                    date_diff(
                        'month',
                        date '{{ var("new_money_goal_from") }}',
                        {{ month }}
                    ) / 12
                ),
                {{ cap }}
            )
    end
{%- endmacro %}
