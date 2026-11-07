-- Each vintage must end exactly when the next begins, never before it starts.
select *
from {{ ref('vintages') }}
where valid_to is not null and valid_to < valid_from
