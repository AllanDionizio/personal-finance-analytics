-- Resolve a raw cell color to a 6-char uppercase hex.
-- rgb:   the ARGB literal minus its alpha byte ('FF4BACC6' -> '4BACC6').
-- theme: the hex of that index in the workbook's own palette, which the
--        caller joins from raw.workbook_themes as `theme_hex`.
{% macro resolve_color_hex(color_type, color_value, theme_hex) -%}
    case
        when {{ color_type }} = 'rgb' then upper(right({{ color_value }}, 6))
        when {{ color_type }} = 'theme' then {{ theme_hex }}
    end
{%- endmacro %}
