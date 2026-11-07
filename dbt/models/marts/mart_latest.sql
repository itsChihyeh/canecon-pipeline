-- Current (latest known) value of every series and reference period.
select series_id, ref_period, value, vintage_number as n_vintages, valid_from as published_at,
       source_snapshot_sha256, source_object_path
from {{ ref('vintages') }}
where valid_to is null
