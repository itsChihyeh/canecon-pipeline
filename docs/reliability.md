# Reliability

How the pipeline behaves when things go wrong, and what was actually checked. Every result below comes from a command that was run; environment: Windows 11, Python 3.12.10, uv 0.11.21, DuckDB 2.0.0, dbt-core 1.12.6, unless it says GitHub Actions.

## Failure rules

| Situation | What happens |
|---|---|
| HTTP 409, 429, 500, 502, 503, 504 or a network error | Retried up to 4 attempts, waiting 2 s, 4 s, 8 s (exponential backoff). |
| Other HTTP errors (e.g. 404) | Not retried; the request fails. |
| HTTP 200 with an unusable body | Treated as a failure (`validate` in `canecon/collect.py`: invalid JSON, StatCan item not `SUCCESS`, empty Valet observations). |
| Some requests of a run fail | The run is `partial`. Its snapshots are kept for audit, but the loader ignores every capture of a run that is not `success`, so no half dataset reaches the warehouse. The day counts as missing. |
| A day is missing | `canecon-catchup` fills it (below). Until then `mart_quality_checks` shows a `missing_collection_days` warning. |
| The collector stops altogether | `hours_since_last_successful_run` > 50 is an error, so the next build fails and the Actions job turns red (GitHub emails the owner). |

## Catch-up

```bash
uv run canecon-catchup --data-dir data/raw                     # every missed day up to today (UTC)
uv run canecon-catchup --data-dir data/raw --date 2026-11-05   # a specific day; repeatable
```

On GitHub: every daily run of the `Daily collect` workflow that collects successfully then runs `canecon-catchup` for all missed days (added 2026-11-11; not yet exercised by a real missed day). To do it by hand, run the workflow with mode `catchup` (and optional `dates`).

Why this was added: the schedule was `0 15 * * *`, and GitHub started the four scheduled runs of 2026-11-07 to 2026-11-10 between 4 and 9 hours late (start times are in `raw/runs.jsonl` on the `data` branch); the 2026-11-09 run started at 23:41 UTC, 19 minutes before it would have been recorded under the next UTC day and left 2026-11-09 missing. The schedule is now `47 13 * * *` (off the hour, earlier, still after StatCan's 08:30 ET release). Whether that shortens the delay is not known yet.

What a catch-up can and cannot do. The APIs serve current data, so nobody can re-capture what an endpoint returned on a past day. A catch-up run therefore:

1. captures everything again now (the same requests as a daily run);
2. asks the Bank of Canada for observations from 14 days before the earliest missed day (`start_date`), in case the gap is longer than the 30 business days a daily run requests;
3. asks StatCan which tables were released on each missed day before today (`getChangedCubeList/<day>`), and records it.

A successful catch-up run lists the days it covers (`for_dates` in `runs.jsonl`), and `mart_collection_coverage` marks them `caught_up`. Consequences of a gap, stated plainly:

- StatCan values keep their official release time, so point-in-time queries stay correct, unless a table was released twice inside the gap (the earlier vintage would be lost). `statcan_series_released` on the coverage row shows whether any of our tables were released on the missed day.
- Bank of Canada values have no release time in the API, so their `published_at` is our capture time. After a gap they look "known" later than they really were. This is conservative: point-in-time queries never use a value before we saw it.

## Fault-injection demo

Offline and reproducible (recorded real responses from `tests/fixtures`, fake clock, no network):

```bash
uv run canecon-demo-failure
```

Output of a real run on 2026-11-07 (abridged; backoff waits are printed, not slept):

```
Day 2 (2026-11-06): daily run with injected faults ['valet=500,500', 'getSeriesInfo=503*']
      injected 503 for the 'getSeriesInfo' request
      backoff: would wait 2s before retrying (skipped in the demo)
      injected 503 for the 'getSeriesInfo' request
      backoff: would wait 4s before retrying (skipped in the demo)
      injected 503 for the 'getSeriesInfo' request
      backoff: would wait 8s before retrying (skipped in the demo)
      injected 503 for the 'getSeriesInfo' request
      injected 500 for the 'valet' request
      backoff: would wait 2s before retrying (skipped in the demo)
      injected 500 for the 'valet' request
      backoff: would wait 4s before retrying (skipped in the demo)
  run status: partial (2/3 requests ok)
  -> this run's data is not loaded; the day counts as missing
...
Before catch-up:
  dbt build (models + tests): ok
  coverage 2026-11-05: collected (1 run(s): success)
  coverage 2026-11-06: missing (1 run(s): partial)
  coverage 2026-11-07: collected (1 run(s): success)
  check missing_collection_days: warn (observed 1) 2026-11-06

Catch-up for missing days ['2026-11-06']
  run status: success (5/5 requests ok)

After catch-up:
  coverage 2026-11-06: caught_up (2 run(s): partial,success, StatCan released that day: unemployment_rate_sa)
  check missing_collection_days: pass (observed 0)
```

The same faults can be injected against the real APIs, for a live demo:

```bash
uv run canecon-collect --data-dir demo/raw --inject-fault valet=500,500 --inject-fault "getSeriesInfo=503*"
uv run canecon-catchup --data-dir demo/raw     # the partial run left today missing
uv run canecon-build --data-dir demo/raw --db demo/wh.duckdb
```

Rule syntax: `KEYWORD=FAULT[,FAULT...]` injects the faults in order into requests whose URL contains KEYWORD, then lets requests through; `KEYWORD=FAULT*` fails every matching request. FAULT is an HTTP status (400-599) or `timeout`. `tests/test_reliability.py` checks the scenario with hand-computed expectations (attempt counts, waits, coverage before and after).

### Two bugs the offline tests did not catch

The first live run of the commands above (2026-11-07, a Saturday, 15:07 UTC) left the catch-up run `partial` (3 of 5 requests ok), so the day stayed missing:

- `boc_observations_since` with `start_date=2026-11-07`: HTTP 200 with an empty `observations` list, rejected by validation. Valet has no observations for a weekend or for today. Fix: start the range 14 days before the earliest missed day.
- `statcan_changed_cubes_2026-11-07`: HTTP 409 on all 4 attempts, body `{"message":"The product is not released yet"}`. StatCan does not answer for the current day. Fix: only ask about days before today (Eastern).

After the fix the same catch-up succeeded (4 of 4 requests) and the day became `caught_up`. Both cases now have tests (`test_catchup_requests_cover_each_missed_day`, `test_catchup_does_not_ask_statcan_about_today`). The offline demo missed them because recorded responses answer every request with 200; validation rejecting an empty 200 is what kept the bad catch-up from counting.

## Data quality checks

`mart_quality_checks` holds one row per (check, subject) with `status` pass / warn / error. The dbt test `assert_no_quality_errors` fails the build on any error; `assert_no_quality_warnings` reports warnings without failing. Thresholds are in `dbt/seeds/series_catalog.csv`.

| Check | Subject | Rule | Level |
|---|---|---|---|
| `ref_period_age_days` | each series | days from the latest reference period to now <= `max_age_days` | error |
| `vintages_out_of_range` | each series | every vintage between `min_value` and `max_value` (catches unit and scale-factor bugs) | error |
| `max_period_to_period_change` | each series | largest change between adjacent periods of the latest values: percent for levels, percentage points for rates | warn above `warn_change`, error above `error_change` |
| `hours_since_last_successful_run` | collector | <= 50 hours | error |
| `missing_collection_days` | collector | no day without a successful run | warn |

The thresholds are judgement calls, not measurements. `max_age_days` follows the release lag: monthly GDP is published about two months after the month ends and the reference period is stored as the first of the month, so the latest GDP period is normally up to about 120 days old (135 allowed). Bank of Canada series are business daily; 7 days allows for long holiday weekends.

Result on the real data (data branch at `774c6fb`, built 2026-11-07): 26 check rows, 25 pass, 1 warning: GDP fell 10.659% in April 2020. That is a real event, which shows the warning works on real data; it stays visible as a known warning.

Tests that a check really fails the build (`tests/test_reliability.py`): GDP values 1000x too large give `vintages_out_of_range` error and a failed build; building ten days after the last run gives errors for the collector and the four daily series, and a failed build.

## Idempotent reruns: checked on GitHub Actions

On 2026-11-07 the `Daily collect` workflow was dispatched twice in a row (runs [42383707191](https://github.com/itsChihyeh/canecon-pipeline/actions/runs/42383707191) and [42383716403](https://github.com/itsChihyeh/canecon-pipeline/actions/runs/42383716403), both success; collector runs started 14:53:38 and 14:54:13 UTC). The data branch went from `b844d00` to `774c6fb`:

| | `b844d00` (before) | `774c6fb` (after two reruns) |
|---|---:|---:|
| object files | 11 | 11 |
| manifest lines | 11 | 17 |
| runs | 2 | 4 |
| observation rows loaded | 12,934 | 13,462 |
| vintages | 2,998 | 2,998 |

Each rerun commit changed only `manifest.jsonl` (+3 lines) and `runs.jsonl` (+1 line); all 6 new captures have `new_object: false` because the responses were byte-identical to the 14:32 run. Rebuilding the warehouse from both commits gave identical `vintages` tables (series, period, vintage number, value, validity interval, source hash compared row by row). More observation rows but the same vintages: repeated captures of the same value are not revisions.

## GitHub's 60-day rule for scheduled workflows

Checked 2026-11-07:

- Official: "In a public repository, scheduled workflows are automatically disabled when no repository activity has occurred in 60 days." ([Disabling and enabling a workflow](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows)). The docs do not define "activity".
- Not official: community answers (e.g. [Stack Overflow 67184368](https://stackoverflow.com/questions/67184368/prevent-scheduled-github-actions-from-becoming-disabled)) report that only commits to the default branch count. If so, the bot's daily commits to the `data` branch do not keep the schedule alive.

Mitigation, not yet verified: every run of `Daily collect` calls `gh workflow enable collect.yml`. In the first scheduled run (42405248838, 2026-11-07 19:14 UTC) the step ran without a warning, so the token has the permission it needs, and the workflow state was `active` afterwards. Whether re-enabling an active workflow resets the 60-day timer is not documented, and can only be seen after 60 days without commits to `main`. Backstops: the owner's commits to `main`; the state can be checked with

```bash
gh api repos/itsChihyeh/canecon-pipeline/actions/workflows/collect.yml --jq .state
```

(`active`, or `disabled_inactivity` once GitHub has stopped it); and `canecon-catchup` fills the days missed while it was off.
