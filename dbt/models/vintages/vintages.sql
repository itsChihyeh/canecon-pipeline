-- One row per distinct published value of (series, reference period).
--
-- Observations are ordered by when they were published, then when we captured them.
-- A row starts a new vintage only if its value differs from the last vintage kept when
-- both are rounded to the coarser of the two precisions, so changes in scale
-- factor or number of decimals alone are not revisions.
with recursive ordered as (
    select
        *,
        row_number() over (
            partition by series_id, ref_period
            order by published_at, captured_at, source_kind
        ) as obs_number
    from {{ ref('stg_observations') }}
),

-- Walk each (series, ref_period) in order, carrying the last value kept as a vintage.
-- Comparing with the last kept vintage, not just the previous observation, matters when
-- precisions are mixed: 100.24, then 100.2 (one decimal, same), then 100.16 is a revision
-- of 100.24 even though it rounds to the same one-decimal value as 100.2.
walk as (
    select
        series_id,
        ref_period,
        obs_number,
        value_scaled as kept_value,
        precision_step as kept_step,
        true as starts_vintage
    from ordered
    where obs_number = 1

    union all

    select
        o.series_id,
        o.ref_period,
        o.obs_number,
        case when c.is_change then o.value_scaled else w.kept_value end,
        case when c.is_change then o.precision_step else w.kept_step end,
        c.is_change
    from walk w
    join ordered o
      on o.series_id = w.series_id
     and o.ref_period = w.ref_period
     and o.obs_number = w.obs_number + 1
    cross join lateral (
        select round(o.value_scaled / greatest(o.precision_step, w.kept_step))
            <> round(w.kept_value / greatest(o.precision_step, w.kept_step)) as is_change
    ) c
),

changes as (
    select o.*
    from ordered o
    join walk w using (series_id, ref_period, obs_number)
    where w.starts_vintage
),

numbered as (
    select
        series_id,
        ref_period,
        row_number() over w as vintage_number,
        value_scaled as value,
        value_reported,
        scalar_factor,
        decimals,
        published_at as valid_from,
        lead(published_at) over w as valid_to,
        captured_at as first_seen_at,
        lead(captured_at) over w as superseded_seen_at,
        source_kind,
        release_label,
        run_id,
        source_snapshot_sha256,
        source_object_path,
        value_scaled - lag(value_scaled) over w as revision_from_previous
    from changes
    window w as (partition by series_id, ref_period order by published_at, captured_at, source_kind)
)

select
    *,
    -- When we can vouch for this value: official vintage tables tell us the publication
    -- time; for live captures we only know it from the moment we first saw it.
    case when source_kind = 'statcan_realtime_table' then valid_from else first_seen_at end
        as observed_from
from numbered
