# Analysis: how much do first releases of monthly GDP get revised?

Question (from the project brief): *How much do first-release estimates of Canada's monthly GDP and retail sales get revised, and how long until they settle?*

Short answer, for GDP only:

- Between the first release and today, month-over-month growth moved by **0.15 percentage points on average** (absolute), across 140 months from January 2015 to August 2026. Revisions were slightly more often up than down (mean +0.03 pp).
- The first release almost always got the **direction** right: first and latest growth have the same sign in 86% of months.
- Estimates **do not fully settle within three years**. For months with at least three years of later releases, the average gap to today's estimate falls from 0.17 pp at the first release to 0.11 pp after a year and 0.07 pp after three years. Most of the movement comes from the annual revisions published each November/December, not from the month right after the first release.
- **Retail sales cannot be answered yet.** Its official real-time table stopped in December 2025 and is not loaded; our own revision history started on 2026-11-07 and has no revisions so far.

## Data and method

- GDP: Statistics Canada Table 36-10-0434-01 (all industries, SAAR, chained dollars), vector v65201210. Revision history from Table 36-10-0491-01 (real-time releases, 140 releases from 2015-03-03 to 2026-09-29), plus our daily captures from 2026-11-07 (first live release: 2026-10-30).
- Growth, not levels: levels in the vintage table jump when Statistics Canada changes the base year of chained dollars (the 30 November 2018 and 30 November 2023 releases), so level revisions mix definitional and economic changes. Month-over-month growth is comparable across base years.
- *First-release growth* uses this month and the previous month as both were known at the first release (`mart_growth_revisions`). *Latest growth* uses today's values. Revision = latest − first, in percentage points (pp).
- *Settling* uses `mart_growth_revision_path`: the growth of each month as known at every later release. It is restricted to months whose first release is at least 36 months before the latest month in the data (January 2015 to August 2023, 104 months), because the latest estimate of recent months is not settled either.
- Months first released before our coverage starts (before the 2015-03-03 release) are excluded, since their first value is unknown.

## Results

### 1. First release vs latest (140 months, 2015-01 to 2026-08)

| Sample | Months | Mean revision (pp) | Median (pp) | Mean absolute (pp) | 90th pct absolute (pp) | Revised up | Revised down | Same sign | Correlation first vs latest |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| All months | 140 | +0.029 | +0.030 | 0.152 | 0.351 | 55.0% | 44.3% | 86.4% | 0.989 |
| Excluding 2020 | 128 | +0.030 | +0.030 | 0.140 | 0.331 | 55.5% | 43.8% | 85.2% | 0.808 |

The remaining 0.7% of months had no revision. The correlation of 0.989 is driven by the huge 2020 swings; without 2020 it is 0.808, a better guide for normal months.

Largest absolute revisions:

| Month | First growth (%) | Latest growth (%) | Revision (pp) |
|---|---:|---:|---:|
| 2020-04 | −11.64 | −10.66 | +0.98 |
| 2021-07 | −0.06 | +0.68 | +0.74 |
| 2021-04 | −0.33 | −1.03 | −0.70 |
| 2020-06 | +6.47 | +5.92 | −0.54 |
| 2024-02 | +0.15 | +0.61 | +0.46 |

July 2021 is the kind of case that matters to a reader: first published as a small decline, now a clear increase.

### 2. How long until estimates settle (104 months, 2015-01 to 2023-08)

| Release number | Mean absolute gap to latest (pp) | Within 0.05 pp of latest | Excluding 2020: mean absolute gap (pp) |
|---:|---:|---:|---:|
| 1 (first release) | 0.170 | 21.2% | 0.155 |
| 2 | 0.168 | 22.1% | 0.152 |
| 3 | 0.142 | 27.9% | 0.133 |
| 6 | 0.131 | 26.0% | 0.126 |
| 12 | 0.114 | 41.3% | 0.105 |
| 24 | 0.090 | 36.5% | 0.093 |
| 36 | 0.072 | 51.0% | 0.073 |

Releases are about one month apart, so release 12 is roughly a year after the first release. The gap shrinks steadily but is still 0.07 pp after three years, and only about half of the months are within 0.05 pp of today's estimate by then.

The revisions are concentrated in a few releases. Summing the absolute change in growth across all months, the largest totals come from the 2023-11-30 release (6.3 pp over 100 months, the comprehensive revision that moved to 2017 dollars), then 2020-12-01, 2025-11-28, 2021-11-30, 2024-11-29 and 2022-11-29: the annual revisions released each November/December.

### 3. Other series

| Series | Revision history starts | Revisions detected (2026-11-07) |
|---|---|---:|
| Retail sales | 2026-11-07 (our first capture) | 0 |
| Unemployment rate | 2026-11-07 | 0 |
| CPI, all-items | 2026-11-07 | 0 |
| Bank of Canada series | 2026-11-07 | 0 |

## Limits

- **One series, one revision regime.** Everything above is about one GDP aggregate. It says nothing yet about retail sales, the other half of the question.
- **Short history for "settling".** Only 104 months have three years of later releases, and the latest of them is itself still subject to future annual revisions, so the settling numbers measure distance to *today's* estimate, not to a final value.
- **2020 dominates averages.** Pandemic months have revisions several times larger than normal; results are shown with and without 2020.
- **Base-year changes are included in growth revisions.** Rebasing changes growth rates a little as well as levels; we do not separate definitional from economic revisions.
- **Coverage assumption.** The vintage table plus our captures are assumed to contain every GDP release since 2015-03 (see [sources.md](sources.md)). A release missing from the table would hide a vintage.
- **Thresholds are choices.** "Within 0.05 pp" and "three years" are judgement calls for presentation, not statistical tests.

## Reproduce

Environment: Windows 11, Python 3.12.10, uv 0.11.21, DuckDB 2.0.0, dbt-core 1.12.6. Data: `data` branch at `53f8060` (collected 2026-11-07 15:12 UTC). Built 2026-11-07.

```bash
git fetch origin data && mkdir -p data/snap && git archive origin/data | tar -x -C data/snap
uv run canecon-build --data-dir data/snap/raw --db data/local/warehouse.duckdb --as-of "2026-11-07 15:30:00"
```

Queries behind the tables (run against `data/local/warehouse.duckdb`):

```sql
-- Table 1 (add "and year(ref_period) <> 2020" for the second row)
select count(*), avg(growth_revision_pp), median(growth_revision_pp), avg(abs(growth_revision_pp)),
       quantile_cont(abs(growth_revision_pp), 0.9),
       avg((growth_revision_pp > 0)::int), avg((growth_revision_pp < 0)::int),
       avg((sign(first_growth_pct) = sign(latest_growth_pct))::int),
       corr(first_growth_pct, latest_growth_pct)
from mart_growth_revisions where series_id = 'gdp_all_industries';

-- Table 2
select release_number, count(*), avg(abs(gap_to_latest_pp)), avg((abs(gap_to_latest_pp) < 0.05)::int)
from mart_growth_revision_path
where series_id = 'gdp_all_industries'
  and ref_period <= (select max(ref_period) from mart_growth_revision_path) - interval 36 month
group by release_number order by release_number;

-- Releases with the most revision
with steps as (
  select released_at,
         abs(growth_pct - lag(growth_pct) over (partition by ref_period order by release_number)) as step
  from mart_growth_revision_path where series_id = 'gdp_all_industries'
)
select cast(released_at as date), sum(step), count(*) filter (where step > 0)
from steps where step is not null group by 1 order by 2 desc limit 8;
```

The dashboard's [Revision explorer](https://itschihyeh.github.io/canecon-pipeline/revisions) draws the same two models and is rebuilt every day, so its numbers move as new releases arrive; the numbers on this page are fixed to the data commit above.
