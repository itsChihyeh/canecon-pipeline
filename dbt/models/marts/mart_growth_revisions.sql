-- Revisions to month-over-month growth, which are comparable across base-year changes.
--
-- first_growth: growth as it was first published. Uses the value of the previous
--   month as it was known at the same publication time (point-in-time, no look-ahead).
-- latest_growth: growth computed from the latest values of both months.
with monthly as (
    select * from {{ ref('vintages') }}
    where series_id in ('gdp_all_industries', 'retail_sales_total_sa')
),

first_rel as (
    select * from {{ ref('mart_first_release') }}
    where is_true_first_release
      and series_id in ('gdp_all_industries', 'retail_sales_total_sa')
),

first_growth as (
    select
        f.series_id,
        f.ref_period,
        f.first_published_at,
        f.first_value / prev.value - 1 as first_growth
    from first_rel f
    join monthly prev
      on prev.series_id = f.series_id
     and prev.ref_period = f.ref_period - interval 1 month
     and prev.valid_from <= f.first_published_at
     and (prev.valid_to is null or prev.valid_to > f.first_published_at)
),

latest as (
    select * from {{ ref('mart_latest') }}
),

latest_growth as (
    select cur.series_id, cur.ref_period, cur.value / prev.value - 1 as latest_growth
    from latest cur
    join latest prev
      on prev.series_id = cur.series_id
     and prev.ref_period = cur.ref_period - interval 1 month
)

select
    g.series_id,
    g.ref_period,
    g.first_published_at,
    round(100 * g.first_growth, 4) as first_growth_pct,
    round(100 * l.latest_growth, 4) as latest_growth_pct,
    round(100 * (l.latest_growth - g.first_growth), 4) as growth_revision_pp
from first_growth g
join latest_growth l using (series_id, ref_period)
