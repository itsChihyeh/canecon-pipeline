---
sidebar_position: 1
title: Revision explorer
---

Official figures change after they are first published. The pipeline keeps every published value
(a *vintage*) of every month, with the time it was published and the raw API response it came from.

```sql series_list
select s.series_id, s.label, count(*) filter (where v.vintage_number > 1) as n_revisions
from canecon.series s join canecon.vintages v using (series_id)
group by all order by n_revisions desc, s.label
```

```sql build
select * from canecon.build_info
```

## Example: real GDP for July 2021

```sql example
select v.vintage_number,
       v.value / 1e9 as value_billions,
       v.revision_from_previous / 1e9 as revision_billions,
       v.valid_from as published_at,
       left(v.source_snapshot_sha256, 12) as snapshot,
       b.snapshot_base_url || v.source_object_path as snapshot_url
from canecon.vintages v cross join canecon.build_info b
where v.series_id = 'gdp_all_industries' and v.ref_period = '2021-07-01'
order by v.vintage_number
```

Each row is one published value of the same month, in billions of chained (2017) dollars, SAAR. Its growth
over June was first published as a decline and is now a clear increase (see the [home page](/)). The jump at
the 30 November 2023 release is a change of base year for chained dollars, not an economic revision.

<DataTable data={example} rows=25>
  <Column id=vintage_number title="Vintage" />
  <Column id=value_billions title="Value" fmt='#,##0.000' />
  <Column id=revision_billions title="Change vs previous" fmt='#,##0.000' />
  <Column id=published_at title="Published (UTC)" fmt='yyyy-mm-dd' />
  <Column id=snapshot_url title="Raw snapshot" contentType=link linkLabel=snapshot openInNewTab=true />
</DataTable>

## Explore any series and month

<Dropdown name=series data={series_list} value=series_id label=label defaultValue="gdp_all_industries" title="Series" />

```sql periods
select ref_period, strftime(ref_period, '%Y-%m-%d') as period_key,
       strftime(ref_period, '%Y-%m-%d') || ' (' || count(*) || ' vintage' || case when count(*) > 1 then 's' else '' end || ')' as period_label
from canecon.vintages
where series_id = '${inputs.series.value}'
group by ref_period
order by ref_period desc
```

<Dropdown name=period data={periods} value=period_key label=period_label title="Reference period" />

```sql scale
select case when max(abs(value)) >= 1e9 then 1e9 when max(abs(value)) >= 1e6 then 1e6 else 1 end as divisor,
       case when max(abs(value)) >= 1e9 then 'billions of ' when max(abs(value)) >= 1e6 then 'millions of ' else '' end
         || (select unit from canecon.series where series_id = '${inputs.series.value}') as unit_label
from canecon.vintages
where series_id = '${inputs.series.value}'
```

```sql history
select v.vintage_number,
       v.value / (select divisor from ${scale}) as value_shown,
       v.revision_from_previous / (select divisor from ${scale}) as revision_shown,
       100 * v.revision_from_previous / lag(v.value) over (order by v.vintage_number) as revision_pct,
       v.valid_from as published_at,
       v.first_seen_at,
       v.source_kind,
       v.release_label,
       left(v.source_snapshot_sha256, 12) as snapshot,
       b.snapshot_base_url || v.source_object_path as snapshot_url
from canecon.vintages v cross join canecon.build_info b
where v.series_id = '${inputs.series.value}'
  and v.ref_period = cast('${inputs.period.value}' as date)
order by v.vintage_number
```

<DataTable data={history} rows=50>
  <Column id=vintage_number title="Vintage" />
  <Column id=value_shown title="Value" fmt='#,##0.000' />
  <Column id=revision_shown title="Change vs previous" fmt='#,##0.000' />
  <Column id=revision_pct title="Change %" fmt='0.000' />
  <Column id=published_at title="Published (UTC)" fmt='yyyy-mm-dd H:MM' />
  <Column id=first_seen_at title="First captured (UTC)" fmt='yyyy-mm-dd H:MM' />
  <Column id=source_kind title="Source" />
  <Column id=snapshot_url title="Raw snapshot" contentType=link linkLabel=snapshot openInNewTab=true />
</DataTable>

Values for this series are in <Value data={scale} column=unit_label />. *Published* is the official release time.
For GDP before 2026-10-30 it comes from the official vintage table 36-10-0491; Bank of Canada series have no
release time in the API, so *published* is our capture time. *Raw snapshot* opens the stored API response
on the `data` branch; its file name is the SHA-256 of its content.

GDP levels jump when Statistics Canada changes the base year of chained dollars (the 30 November 2018
and 30 November 2023 releases), so level changes are not all economic revisions. The analysis below uses growth rates.

## GDP growth: first release vs now

```sql growth
select ref_period, first_growth_pct, latest_growth_pct, growth_revision_pp
from canecon.growth_revisions where series_id = 'gdp_all_industries' order by ref_period
```

```sql growth_long
select ref_period, 'First release' as estimate, first_growth_pct as growth_pct from ${growth}
union all
select ref_period, 'Latest estimate', latest_growth_pct from ${growth}
```

<LineChart data={growth_long} x=ref_period y=growth_pct series=estimate yAxisTitle="month-over-month growth, %" yFmt='0.0' />

<BarChart data={growth} x=ref_period y=growth_revision_pp yAxisTitle="revision, percentage points" yFmt='0.00' title="Latest minus first-release growth" />

First-release growth uses the previous month *as it was known at the same release*, so it is the growth a
reader could have computed on release day. Months whose first release happened before our coverage starts
(March 2015) are left out.

## How long until GDP growth settles?

```sql settle
select release_number,
       count(*) as months,
       avg(abs(gap_to_latest_pp)) as mean_abs_gap_pp,
       avg(abs(change_since_first_pp)) as mean_abs_change_pp
from canecon.growth_revision_path
where series_id = 'gdp_all_industries'
  and ref_period <= (select max(ref_period) from canecon.growth_revision_path) - interval 36 month
  and release_number <= 37
group by release_number
order by release_number
```

```sql settle_summary
select min(ref_period) as first_month, max(ref_period) as last_month, count(distinct ref_period) as months
from canecon.growth_revision_path
where series_id = 'gdp_all_industries'
  and ref_period <= (select max(ref_period) from canecon.growth_revision_path) - interval 36 month
```

<LineChart data={settle} x=release_number y=mean_abs_gap_pp yAxisTitle="mean absolute gap to latest, pp" xAxisTitle="release number (1 = first release, about one month apart)" yFmt='0.000' />

For each month from <Value data={settle_summary} column=first_month fmt='mmm yyyy' /> to
<Value data={settle_summary} column=last_month fmt='mmm yyyy' /> (<Value data={settle_summary} column=months /> months,
all with at least three years of later releases), this shows how far its growth estimate at each release was
from today's estimate. Months from the last three years are left out because their latest estimate is not
settled yet. See the [analysis](https://github.com/itsChihyeh/canecon-pipeline/blob/main/docs/analysis.md) for what this does and does not show.

## Other series

Retail sales, CPI, the unemployment rate and the daily Bank of Canada series have no official vintage history
that we load, so their revision history starts with our first capture on 2026-11-07. Vintages after the first one, per series (for GDP this includes base-year changes):

<DataTable data={series_list}>
  <Column id=label title="Series" />
  <Column id=n_revisions title="Vintages after the first" />
</DataTable>

<Attribution />
