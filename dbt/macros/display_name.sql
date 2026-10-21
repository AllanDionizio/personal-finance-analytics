-- The label a dashboard shows for an owner or a card. The repo only knows
-- the placeholders ('Person A', 'Card B'); a local run can map them to real
-- names through env var DISPLAY_NAMES, a JSON object such as
-- {"Person A": "Ana"}, kept in the gitignored .env.real. Without it, the
-- label is the placeholder itself.
{% macro display_name(column) -%}
    {%- set names = fromjson(env_var('DISPLAY_NAMES', '{}')) -%}
    {%- if names -%}
        case {{ column }}
            {%- for placeholder, name in names.items() %}
            when '{{ placeholder | replace("'", "''") }}' then '{{ name | replace("'", "''") }}'
            {%- endfor %}
            else {{ column }}
        end
    {%- else -%}
        {{ column }}
    {%- endif -%}
{%- endmacro %}
