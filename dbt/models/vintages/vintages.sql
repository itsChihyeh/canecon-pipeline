-- One row per distinct published value of (series, reference period).
--
-- Observations are ordered by when they were published, then when we captured them.
-- A row starts a new vintage only if its value differs from the previous one when
-- both are rounded to the coarser of the two precisions, so changes in scale
-- factor or number of decimals alone are not revisions.
with ordered as (
    select
        *,
        lag(value_scaled) over w as prev_value_scaled,
        lag(precision_step) over w as prev_precision_step
    from {{ ref('stg_observations') }}
    window w as (
        partition by series_id, ref_period
        order by published_at, captured_at, source_kind
    )
),

flagged as (
    select
        *,
        greatest(precision_step, coalesce(prev_precision_step, precision_step)) as compare_step
    from ordered
),

changes as (
    select *
    from flagged
    where prev_value_scaled is null
       or round(value_scaled / compare_step) <> round(prev_value_scaled / compare_step)
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
