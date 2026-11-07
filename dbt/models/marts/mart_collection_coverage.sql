-- One row per collection day (UTC) from the first daily run up to the reference time.
--
-- A day is covered when at least one successful run lists it in raw.run_days: the
-- daily run of that day, or a later catch-up run. Partial and failed runs never cover
-- a day, because their data is not used.
--
-- statcan_series_released: which of our StatCan series' tables changed that day, as
-- reported by getChangedCubeList during a catch-up run ('' = none of ours; null = not
-- asked, which is the case for normal days).
with as_of as (
    select {{ quality_as_of() }} as as_of
),

first_day as (
    select min(cast(started_at as date)) as first_day
    from {{ source('raw', 'runs') }}
    where kind = 'daily'
),

days as (
    select cast(unnest(generate_series(f.first_day, cast(a.as_of as date), interval 1 day)) as date)
        as collection_day
    from first_day f, as_of a
    where f.first_day is not null
),

day_runs as (
    select rd.collection_day, r.run_id, r.kind, r.status, r.started_at
    from {{ source('raw', 'run_days') }} rd
    join {{ source('raw', 'runs') }} r using (run_id)
),

per_day as (
    select
        collection_day,
        count(*) as n_runs,
        count(*) filter (where status = 'success') as n_successful_runs,
        coalesce(bool_or(kind = 'daily' and status = 'success'), false) as daily_ok,
        coalesce(bool_or(kind = 'catchup' and status = 'success'), false) as catchup_ok,
        min(started_at) filter (where status = 'success') as first_success_at,
        string_agg(distinct status, ',' order by status) as run_statuses
    from day_runs
    group by collection_day
),

asked as (
    select distinct
        cast(substr(c.request_id, length('statcan_changed_cubes_') + 1) as date) as collection_day
    from {{ source('raw', 'captures') }} c
    join {{ source('raw', 'runs') }} r using (run_id)
    where starts_with(c.request_id, 'statcan_changed_cubes_')
      and c.ok and r.status = 'success'
),

released as (
    select
        ct.day as collection_day,
        string_agg(distinct c.series_id, ',' order by c.series_id) as statcan_series_released
    from {{ source('raw', 'changed_tables') }} ct
    join {{ ref('series_catalog') }} c on c.product_id = ct.product_id
    group by ct.day
)

select
    d.collection_day,
    case
        when p.daily_ok then 'collected'
        when p.catchup_ok then 'caught_up'
        when d.collection_day = cast(a.as_of as date) then 'pending'
        else 'missing'
    end as status,
    coalesce(p.n_runs, 0) as n_runs,
    coalesce(p.n_successful_runs, 0) as n_successful_runs,
    p.run_statuses,
    p.first_success_at,
    case when k.collection_day is not null then coalesce(rel.statcan_series_released, '') end
        as statcan_series_released
from days d
cross join as_of a
left join per_day p using (collection_day)
left join asked k using (collection_day)
left join released rel using (collection_day)
order by d.collection_day
