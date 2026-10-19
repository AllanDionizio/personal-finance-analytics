-- Macro-category as typed in the workbooks ('Fixo', 'Variável', 'n/a') to
-- the English label the models use. Anything else becomes NULL.
{% macro translate_macro_category(column) -%}
    case {{ column }}
        when 'Fixo' then 'Fixed'
        when 'Variável' then 'Variable'
        when 'n/a' then 'Not applicable'
    end
{%- endmacro %}
