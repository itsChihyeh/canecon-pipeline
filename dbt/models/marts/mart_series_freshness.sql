-- How old each series' latest reference period is, against its expected release lag.
-- ref_period_age_days = reference time - latest ref_period (first day of the month for
-- monthly series). max_age_days in seeds/series_catalog.csv is the oldest that is still
-- normal, e.g. 135 for GDP, which is published about two months after the month ends.
with as_of as (
    select {{ quality_as_of() }} as as_of
),

latest as (
    select series_id, max(ref_period) as latest_ref_period, max(published_at) as last_published_at
    from {{ ref('mart_latest') }}
    group by series_id
),

seen as (
    select series_id, max(captured_at) as last_captured_at
    from {{ ref('stg_observations') }}
    group by series_id
)

select
    c.series_id,
    c.source,
    c.frequency,
    c.max_age_days,
    l.latest_ref_period,
    l.last_published_at,
    s.last_captured_at,
    date_diff('day', l.latest_ref_period, cast(a.as_of as date)) as ref_period_age_days,
    coalesce(date_diff('day', l.latest_ref_period, cast(a.as_of as date)) <= c.max_age_days, false) as is_fresh,
    a.as_of as checked_as_of
from {{ ref('series_catalog') }} c
cross join as_of a
left join latest l using (series_id)
left join seen s using (series_id)
