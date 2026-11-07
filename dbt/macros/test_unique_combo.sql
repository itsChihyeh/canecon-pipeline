{% test dbt_utils_free_unique_combo(model, columns) %}
-- Fails if any combination of the given columns appears more than once.
select {{ columns | join(', ') }}, count(*) as n
from {{ model }}
group by {{ columns | join(', ') }}
having count(*) > 1
{% endtest %}
