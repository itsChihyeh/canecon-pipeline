---
sidebar_position: 3
title: Data quality
---

How fresh the data is and whether the latest build passed its checks. Checks ran as of
<Value data={build} column=quality_checked_as_of fmt='yyyy-mm-dd H:MM' /> UTC.

```sql build
select * from canecon.build_info
```

```sql check_counts
select count(*) filter (where status = 'pass') as passed,
       count(*) filter (where status = 'warn') as warnings,
       count(*) filter (where status = 'error') as errors
from canecon.quality_checks
```

```sql run_counts
select count(*) as runs,
       count(*) filter (where status = 'success') as successful_runs
from canecon.runs
```

<BigValue data={check_counts} value=passed title="Checks passed" />
<BigValue data={check_counts} value=warnings title="Warnings" />
<BigValue data={check_counts} value=errors title="Errors" />
<BigValue data={run_counts} value=successful_runs title="Successful collector runs" />

An error fails the build in GitHub Actions; a warning is shown here and in the build log but does not.

## Checks

```sql checks
select status, check_name, subject, ref_period, observed, lower_bound, upper_bound, detail
from canecon.quality_checks
order by case status when 'error' then 0 when 'warn' then 1 else 2 end, check_name, subject
```

<DataTable data={checks} rows=50>
  <Column id=status />
  <Column id=check_name title="Check" />
  <Column id=subject />
  <Column id=observed fmt='#,##0.00' />
  <Column id=lower_bound title="Min" fmt='#,##0.00' />
  <Column id=upper_bound title="Max" fmt='#,##0.00' />
  <Column id=detail />
</DataTable>

The thresholds are judgement calls, not measurements. They are listed in
[series_catalog.csv](https://github.com/itsChihyeh/canecon-pipeline/blob/main/dbt/seeds/series_catalog.csv) and explained in
[reliability.md](https://github.com/itsChihyeh/canecon-pipeline/blob/main/docs/reliability.md).

## Freshness by series

```sql freshness
select s.label, f.latest_ref_period, f.ref_period_age_days, f.max_age_days, f.is_fresh,
       f.last_published_at, f.last_captured_at
from canecon.series_freshness f join canecon.series s using (series_id)
order by s.label
```

<DataTable data={freshness}>
  <Column id=label title="Series" />
  <Column id=latest_ref_period title="Latest period" fmt='yyyy-mm-dd' />
  <Column id=ref_period_age_days title="Age (days)" />
  <Column id=max_age_days title="Allowed (days)" />
  <Column id=is_fresh title="Fresh" />
  <Column id=last_published_at title="Last published (UTC)" fmt='yyyy-mm-dd H:MM' />
  <Column id=last_captured_at title="Last captured (UTC)" fmt='yyyy-mm-dd H:MM' />
</DataTable>

Monthly series are published weeks after the month ends (GDP about two months later), and their age is
measured from the first day of the reference month. For Bank of Canada series, *last published* is our
capture time, because the API gives no release time.

## Collection days

```sql coverage
select collection_day, status, n_runs, n_successful_runs, run_statuses, first_success_at, statcan_series_released
from canecon.collection_coverage order by collection_day desc
```

<DataTable data={coverage} rows=30>
  <Column id=collection_day title="Day (UTC)" fmt='yyyy-mm-dd' />
  <Column id=status />
  <Column id=n_runs title="Runs" />
  <Column id=n_successful_runs title="Successful" />
  <Column id=run_statuses title="Run statuses" />
  <Column id=first_success_at title="First success (UTC)" fmt='H:MM' />
  <Column id=statcan_series_released title="Our StatCan tables released that day" />
</DataTable>

*collected*: a successful daily run that day. *caught_up*: filled later by a catch-up run. *missing*: no
successful run yet. A run where any request failed is kept for audit but never loaded.

## Collector runs

```sql runs
select started_at, kind, status, n_ok, n_requests,
       date_diff('second', started_at, finished_at) as seconds
from canecon.runs order by started_at desc
```

<DataTable data={runs} rows=30>
  <Column id=started_at title="Started (UTC)" fmt='yyyy-mm-dd H:MM' />
  <Column id=kind />
  <Column id=status />
  <Column id=n_ok title="Requests ok" />
  <Column id=n_requests title="Requests" />
  <Column id=seconds title="Seconds" />
</DataTable>

## Last success per request

```sql requests
select request_id, last_success_at, last_attempt_at, n_failed_attempts
from canecon.request_freshness order by request_id
```

<DataTable data={requests} rows=30>
  <Column id=request_id title="Request" />
  <Column id=last_success_at title="Last success (UTC)" fmt='yyyy-mm-dd H:MM' />
  <Column id=last_attempt_at title="Last attempt (UTC)" fmt='yyyy-mm-dd H:MM' />
  <Column id=n_failed_attempts title="Failed attempts" />
</DataTable>

<Attribution />
