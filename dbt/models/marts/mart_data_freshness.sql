-- Last successful capture per source request and the latest run status.
select
    c.request_id,
    max(c.captured_at) filter (where c.ok) as last_success_at,
    max(c.captured_at) as last_attempt_at,
    count(*) filter (where not c.ok) as n_failed_attempts
from {{ source('raw', 'captures') }} c
group by c.request_id
