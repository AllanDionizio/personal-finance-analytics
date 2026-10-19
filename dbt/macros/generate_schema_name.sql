-- Use the custom schema name as is (staging, marts) instead of dbt's
-- default <target_schema>_<custom_schema>, so the warehouse reads
-- staging.stg_transactions rather than main_staging.stg_transactions.
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
