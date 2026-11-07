-- First value we have for each (series, reference period).
--
-- is_true_first_release: we observed the series before this reference period first
-- appeared, so this really is the first published value. False for periods that were
-- already published before our coverage of the series started (we cannot know whether
-- they had been revised before that). Assumes our coverage has no gaps between releases.
with v as (
    select
        *,
        min(observed_from) over (partition by series_id) as series_coverage_start
    from {{ ref('vintages') }}
)

select
    series_id,
    ref_period,
    value as first_value,
    valid_from as first_published_at,
    observed_from > series_coverage_start as is_true_first_release,
    source_kind,
    source_snapshot_sha256
from v
where vintage_number = 1
