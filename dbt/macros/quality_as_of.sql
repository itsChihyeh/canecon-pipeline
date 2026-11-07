{% macro quality_as_of() %}
{#- Reference time (naive UTC timestamp) for freshness checks: var quality_as_of, else now. -#}
{%- if var('quality_as_of') -%}
cast('{{ var("quality_as_of") }}' as timestamp)
{%- else -%}
cast(timezone('UTC', now()) as timestamp)
{%- endif -%}
{% endmacro %}
