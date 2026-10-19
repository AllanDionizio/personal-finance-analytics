-- Description without its installment tag, same rules as
-- ingestion/installment_parser.py: drop the first "(N/M)", collapse
-- whitespace (with or without a tag), and fix the "A - - B" left by a tag
-- between two dashes.
{% macro clean_description(column) -%}
    trim(
        replace(
            regexp_replace(
                regexp_replace({{ column }}, '\s*\(\d+\s*/\s*\d+\)\s*', ' '),
                '\s+', ' ', 'g'
            ),
            ' - - ', ' - '
        )
    )
{%- endmacro %}
