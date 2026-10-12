{% macro length_band(duration_secs) %}
    case
        when {{ duration_secs }} is null then null
        when {{ duration_secs }} <= 180 then '0-3 min'
        when {{ duration_secs }} <= 600 then '3-10 min'
        when {{ duration_secs }} <= 1200 then '10-20 min'
        when {{ duration_secs }} <= 2400 then '20-40 min'
        else '40+ min'
    end
{% endmacro %}