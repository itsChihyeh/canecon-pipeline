---
sidebar_position: 2
title: Point in time
---

What did the official numbers say on a past day, and what do they say now? Pick a date: every value below
is the vintage that was published by the end of that day (UTC) and not yet replaced. Nothing published later
is used.

```sql dates
select strftime(d, '%Y-%m-%d') as day
from (
    select cast(range as date) - interval 1 day as d
    from range(date '2015-04-01', (select cast(built_at as date) from canecon.build_info) + interval 1 month, interval 1 month)
)
where d <= (select cast(built_at as date) from canecon.build_info)
union
select strftime(cast(built_at as date), '%Y-%m-%d') from canecon.build_info
order by day desc
```

<Dropdown name=asof data={dates} value=day defaultValue="2020-06-30" title="As of (end of day, UTC)" />

Dates are month-ends from March 2015, plus the latest build day.

```sql known_then
select v.series_id, v.ref_period, v.value as value_then, v.vintage_number, v.valid_from
from canecon.vintages v
where v.valid_from < cast('${inputs.asof.value}' as date) + interval 1 day
  and (v.valid_to is null or v.valid_to >= cast('${inputs.asof.value}' as date) + interval 1 day)
```

```sql compare
with last_known as (
    select * from ${known_then}
    qualify row_number() over (partition by series_id order by ref_period desc) = 1
)
select s.label,
       k.ref_period as latest_period_then,
       k.value_then,
       l.value as value_now,
       l.value - k.value_then as difference,
       k.valid_from as published_at
from canecon.series s
join last_known k using (series_id)
join canecon.latest l on l.series_id = k.series_id and l.ref_period = k.ref_period
order by s.label
```

## Latest figure known on that day, and the same figure now

<DataTable data={compare}>
  <Column id=label title="Series" />
  <Column id=latest_period_then title="Latest period then" fmt='yyyy-mm-dd' />
  <Column id=value_then title="Value then" fmt='#,##0.00' />
  <Column id=value_now title="Same period now" fmt='#,##0.00' />
  <Column id=difference title="Difference" fmt='#,##0.00' />
  <Column id=published_at title="Published (UTC)" fmt='yyyy-mm-dd' />
</DataTable>

Only GDP has history before 2026-11-07 (from the official vintage table 36-10-0491); other series appear for
dates from 2026-11-07 on, when collection started. GDP levels before December 2023 are in older base-year
dollars, so compare growth rates below rather than levels.

## GDP growth as known then vs now

```sql gdp_growth
with known as (
    select ref_period, 100 * (value_then / lag(value_then) over (order by ref_period) - 1) as g
    from ${known_then} where series_id = 'gdp_all_industries'
),
now as (
    select ref_period, 100 * (value / lag(value) over (order by ref_period) - 1) as g
    from canecon.latest where series_id = 'gdp_all_industries'
)
select t.ref_period, 'As known then' as estimate, t.g as growth_pct
from known t
where t.g is not null and t.ref_period >= (select max(ref_period) from known) - interval 24 month
union all
select n.ref_period, 'As known now', n.g
from now n
where n.ref_period >= (select max(ref_period) from known) - interval 24 month
  and n.ref_period <= (select max(ref_period) from known)
order by 1
```

<LineChart data={gdp_growth} x=ref_period y=growth_pct series=estimate yAxisTitle="month-over-month growth, %" yFmt='0.0' />

The 24 months up to the latest month that had been published on the chosen date.

<Attribution />
