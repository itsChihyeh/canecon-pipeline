-- Data quality checks, one row per (check, subject). status: pass / warn / error.
-- dbt tests fail the build on any 'error' row and report 'warn' rows as warnings
-- (tests/assert_no_quality_errors.sql, tests/assert_no_quality_warnings.sql).
-- Thresholds live in seeds/series_catalog.csv.
with as_of as (
    select {{ quality_as_of() }} as as_of
),

catalog as (
    select * from {{ ref('series_catalog') }}
),

-- 1. Freshness: the latest reference period is not older than the series allows.
freshness as (
    select
        'ref_period_age_days' as check_name,
        series_id as subject,
        latest_ref_period as ref_period,
        cast(ref_period_age_days as double) as observed,
        cast(null as double) as lower_bound,
        cast(max_age_days as double) as upper_bound,
        case when is_fresh then 'pass' else 'error' end as status,
        case when latest_ref_period is null then 'no data for this series' end as detail
    from {{ ref('mart_series_freshness') }}
),

-- 2. Value range: every vintage ever loaded lies inside plausible bounds
--    (catches unit or scale-factor bugs, e.g. GDP off by 1000x).
range_violations as (
    select
        v.series_id,
        count(*) filter (where v.value < c.min_value or v.value > c.max_value) as n_out,
        min(v.ref_period) filter (where v.value < c.min_value or v.value > c.max_value) as first_out,
        any_value(c.min_value) as min_value,
        any_value(c.max_value) as max_value
    from {{ ref('vintages') }} v
    join catalog c using (series_id)
    group by v.series_id
),

value_range as (
    select
        'vintages_out_of_range' as check_name,
        series_id as subject,
        first_out as ref_period,
        cast(n_out as double) as observed,
        cast(min_value as double) as lower_bound,
        cast(max_value as double) as upper_bound,
        case when n_out = 0 then 'pass' else 'error' end as status,
        case when n_out > 0 then n_out || ' vintage(s) outside bounds, first at ' || first_out end as detail
    from range_violations
),

-- 3. Jumps: change between adjacent periods of the latest values. Percent change for
--    levels, absolute change (percentage points) for rates. Warn above warn_change,
--    error above error_change.
steps as (
    select
        l.series_id,
        l.ref_period,
        case c.change_kind
            when 'pct' then abs(l.value / lag(l.value) over w - 1) * 100
            else abs(l.value - lag(l.value) over w)
        end as change,
        c.warn_change,
        c.error_change,
        c.change_kind
    from {{ ref('mart_latest') }} l
    join catalog c using (series_id)
    window w as (partition by l.series_id order by l.ref_period)
),

largest_step as (
    select
        series_id,
        max(change) as max_change,
        arg_max(ref_period, change) as at_period,
        any_value(warn_change) as warn_change,
        any_value(error_change) as error_change,
        any_value(change_kind) as change_kind
    from steps
    where change is not null
    group by series_id
),

jumps as (
    select
        'max_period_to_period_change' as check_name,
        series_id as subject,
        at_period as ref_period,
        round(cast(max_change as double), 4) as observed,
        cast(warn_change as double) as lower_bound,
        cast(error_change as double) as upper_bound,
        case
            when max_change > error_change then 'error'
            when max_change > warn_change then 'warn'
            else 'pass'
        end as status,
        'largest change ' || round(cast(max_change as double), 3)
            || case change_kind when 'pct' then '%' else ' pp' end || ' at ' || at_period as detail
    from largest_step
),

-- 4. The collector is still running: hours since the last successful daily or catch-up run.
last_run as (
    select max(finished_at) as last_success
    from {{ source('raw', 'runs') }}
    where status = 'success' and kind in ('daily', 'catchup')
),

collector as (
    select
        'hours_since_last_successful_run' as check_name,
        'collector' as subject,
        cast(null as date) as ref_period,
        round(date_diff('minute', r.last_success, a.as_of) / 60.0, 1) as observed,
        cast(null as double) as lower_bound,
        50.0 as upper_bound,
        case when r.last_success is not null and date_diff('minute', r.last_success, a.as_of) <= 50 * 60
             then 'pass' else 'error' end as status,
        cast(null as varchar) as detail
    from last_run r, as_of a
),

-- 5. Gaps: collection days with no successful run (fill them with canecon-catchup).
gaps as (
    select
        'missing_collection_days' as check_name,
        'collector' as subject,
        min(collection_day) filter (where status = 'missing') as ref_period,
        cast(count(*) filter (where status = 'missing') as double) as observed,
        cast(null as double) as lower_bound,
        0.0 as upper_bound,
        case when count(*) filter (where status = 'missing') = 0 then 'pass' else 'warn' end as status,
        string_agg(cast(collection_day as varchar), ', ' order by collection_day)
            filter (where status = 'missing') as detail
    from {{ ref('mart_collection_coverage') }}
)

select *, (select as_of from as_of) as checked_as_of
from (
    select * from freshness
    union all select * from value_range
    union all select * from jumps
    union all select * from collector
    union all select * from gaps
)
order by check_name, subject
