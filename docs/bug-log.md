# Bug log

Real problems found while building this project, how they showed up, and what fixed them. Only things that actually happened are listed.

## 1. Catch-up asked the Bank of Canada for a range with no data (2026-11-07)

- **Symptom:** the first live catch-up run (a Saturday, 15:07 UTC) ended `partial`; the missed day stayed missing.
- **Cause:** the Valet request used `start_date` = the missed day itself. Valet answered HTTP 200 with an empty `observations` list, because there are no observations for a weekend or for the current day. Validation correctly rejected the empty 200 as unusable, so the run did not count.
- **Fix:** start the range 14 days before the earliest missed day. Test: `test_catchup_requests_cover_each_missed_day`.
- **Why tests missed it:** the offline tests replay recorded responses, which return 200 with data for every request.

## 2. StatCan refuses questions about today (2026-11-07)

- **Symptom:** in the same run, `getChangedCubeList/2026-11-07` returned HTTP 409 on all 4 attempts, body `{"message":"The product is not released yet"}`.
- **Cause:** the catch-up asked StatCan which tables were released on each missed day, including the current day, which StatCan does not answer.
- **Fix:** only ask about days before today in Eastern time. Test: `test_catchup_does_not_ask_statcan_about_today`. After both fixes the same catch-up succeeded (4 of 4 requests) and the day became `caught_up`.

Details and the run output: [reliability.md](reliability.md).

## 3. The dashboard could not read the warehouse file (P4)

- **Symptom:** pointing the dashboard straight at the warehouse fails when Evidence loads its sources. Reproduced on 2026-11-07 by copying the warehouse over the export file and running `npm run sources:strict`:

  ```
  [ ! ] Error connecting to datasource canecon: IO Error: Trying to read a database file with version number 999, but we can only read versions between 64 and 67.
  The database file was created with an newer version of DuckDB.
  ```

- **Cause:** the pipeline uses DuckDB 2.0 (Python); the Evidence DuckDB connector bundles DuckDB 1.4, which cannot read the newer storage format.
- **Fix:** `canecon-export` attaches a new file with `STORAGE_VERSION 'v1.4.0'` and copies the public tables into it. This also became the place where non-public series are filtered out (see [design-decisions.md](design-decisions.md), decision 6).

## 4. A test could not copy the database on Windows (P4)

- **Symptom:** the export test builds a warehouse with dbt and then exports it. The export could not open the freshly built file, and copying the file first also failed on Windows because the file was still in use. The exact error text was not kept.
- **Cause:** dbt, run in the same test process, keeps its connection to the DuckDB file open after the build; Windows does not let another handle copy a file held open that way.
- **Fix:** the test copies the data inside DuckDB instead of copying the file (`copy from database wh to wh_copy`, `tests/test_export.py`) and exports from the copy. In the pipeline the export runs as its own process, so the problem does not arise there.

## 5. Mixed precisions could hide a revision (found in review, 2026-11-07)

- **Symptom:** none in the real data. A code review asked what happens when releases of the same month use different numbers of decimals. A hand-built case showed it: 100.24, then 100.2 (one decimal), then 100.16 gave one vintage instead of two.
- **Cause:** `vintages.sql` compared each observation with the observation just before it (`LAG`). 100.2 matches 100.24 at one decimal, and 100.16 matches 100.2 at one decimal, so the change from 100.24 to 100.16 was never compared directly.
- **Fix:** a recursive CTE carries the last value kept as a vintage and compares each new observation with it. Test: `test_mixed_precision_compares_with_last_kept_vintage`, which failed before the fix. Rebuilding from the `data` snapshots at `53f8060` gave the same 2,968 vintages as before the fix.
