-- Two consecutive vintages must have different values (otherwise it is not a revision).
select *
from {{ ref('vintages') }}
where vintage_number > 1 and revision_from_previous = 0
