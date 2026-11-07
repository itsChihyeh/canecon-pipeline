-- Every vintage must point to a raw snapshot that exists in the capture log.
select v.*
from {{ ref('vintages') }} v
left join {{ source('raw', 'captures') }} c
  on c.content_sha256 = v.source_snapshot_sha256 and c.run_id = v.run_id
where c.content_sha256 is null
