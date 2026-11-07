-- How the month-over-month growth of each month changed release by release.
--
-- One row per (series, ref_period, release) from the month's first release onward.
-- A release is a distinct publication time seen for the series in successful captures,
-- whether or not it changed this month's value. growth_pct uses both months as they
-- were known at that release (point-in-time, no look-ahead), so release_number = 1
-- matches first_growth_pct in mart_growth_revisions.
with monthly as (
    select * from {{ ref('vintages') }}
    where series_id in ('gdp_all_industries', 'retail_sales_total_sa')
),

releases as (
    select distinct series_id, published_at as released_at
    from {{ ref('stg_observations') }}
    where series_id in ('gdp_all_industries', 'retail_sales_total_sa')
),

firsts as (
    select series_id, ref_period, first_published_at
    from {{ ref('mart_first_release') }}
    where is_true_first_release
      and series_id in ('gdp_all_industries', 'retail_sales_total_sa')
),

path as (
    select
        f.series_id,
        f.ref_period,
        r.released_at,
        cur.value / prev.value - 1 as growth
    from firsts f
    join releases r
      on r.series_id = f.series_id
     and r.released_at >= f.first_published_at
    join monthly cur
      on cur.series_id = f.series_id
     and cur.ref_period = f.ref_period
     and cur.valid_from <= r.released_at
     and (cur.valid_to is null or cur.valid_to > r.released_at)
    join monthly prev
      on prev.series_id = f.series_id
     and prev.ref_period = f.ref_period - interval 1 month
     and prev.valid_from <= r.released_at
     and (prev.valid_to is null or prev.valid_to > r.released_at)
),

numbered as (
    select
        *,
        row_number() over (partition by series_id, ref_period order by released_at) as release_number,
        first_value(growth) over (partition by series_id, ref_period order by released_at) as first_growth,
        last_value(growth) over (
            partition by series_id, ref_period order by released_at
            rows between unbounded preceding and unbounded following
        ) as latest_growth
    from path
)

select
    series_id,
    ref_period,
    release_number,
    released_at,
    round(100 * growth, 4) as growth_pct,
    round(100 * (growth - first_growth), 4) as change_since_first_pp,
    round(100 * (latest_growth - growth), 4) as gap_to_latest_pp
from numbered
