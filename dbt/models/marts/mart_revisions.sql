-- How much each reference period's LEVEL moved from its first release to its latest value.
-- Caution: level revisions include base-year changes (e.g. GDP re-based from 2012 to
-- 2017 chained dollars in Dec 2023), which shift every level without changing the
-- economy's story. Use mart_growth_revisions to analyse revisions.
-- Only periods whose first release we actually observed are included.
with first_rel as (
    select * from {{ ref('mart_first_release') }} where is_true_first_release
),

last_rev as (
    select series_id, ref_period, max(valid_from) as last_revised_at
    from {{ ref('vintages') }}
    where vintage_number > 1
    group by series_id, ref_period
)

select
    f.series_id,
    f.ref_period,
    f.first_value,
    l.value as latest_value,
    l.n_vintages - 1 as n_revisions,
    l.value - f.first_value as total_revision,
    case when f.first_value <> 0
         then round(100 * (l.value - f.first_value) / abs(f.first_value), 4) end as total_revision_pct,
    f.first_published_at,
    r.last_revised_at,
    date_diff('day', f.first_published_at, r.last_revised_at) as days_first_to_last_revision
from first_rel f
join {{ ref('mart_latest') }} l using (series_id, ref_period)
left join last_rev r using (series_id, ref_period)
