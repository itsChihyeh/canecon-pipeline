# Design decisions

Each entry: what was chosen, what else was possible, and why. "Would change if" says what would make the other option better.

## 1. DuckDB, not PostgreSQL or a cloud warehouse

- **Chosen:** DuckDB, a single-file analytical database, rebuilt from the raw snapshots on every run.
- **Alternatives:** PostgreSQL (a server to run and pay for, or a free tier with limits); BigQuery or Snowflake (accounts, credentials in CI, cost control).
- **Why:** the whole warehouse is about 13,800 observation rows and builds in under a minute on a laptop (the dbt models and tests themselves take about 3 seconds). DuckDB runs inside the Python process and inside GitHub Actions with no service, no credentials and no cost. Because the warehouse is rebuilt from scratch, there is no migration or state to manage: delete the file and build again.
- **Would change if:** several people or services had to query the warehouse at the same time, or the data grew past what one machine can rebuild in minutes. Then a server or cloud warehouse (and incremental models) would pay off.

## 2. Raw snapshots in a git branch, not a database or cloud bucket

- **Chosen:** the collector commits responses to the `data` branch of the same public repository: `objects/<sha256>`, plus `manifest.jsonl` and `runs.jsonl`.
- **Alternatives:** store raw responses in the warehouse itself; S3 or Google Cloud Storage.
- **Why:** the raw layer must be append-only and auditable. Git gives that for free: every collection is a commit, history cannot be changed silently, and anyone can download the exact bytes behind a number. Content-addressed file names make reruns idempotent (the same response is the same file). It costs nothing and needs no cloud account. Keeping it on a separate branch keeps bot commits out of `main`.
- **Would change if:** the snapshots grew large (git is poor at many big binary files), or the data had to be private. A bucket with object versioning would then be the natural replacement, with the same content-addressed layout.
- **Known cost:** whatever is committed to the public branch is public for good. This matters for the USD/CAD series (decision 6).

## 3. Rebuild everything instead of incremental loads

- **Chosen:** `canecon-build` reloads all successful snapshots and runs every dbt model from scratch.
- **Alternatives:** incremental dbt models or an SCD2 table updated in place.
- **Why:** with this data size a full rebuild is fast, and it removes a class of bugs (a half-applied update, an out-of-order capture). Idempotency is then easy to check: two builds from the same snapshots must give identical tables, which was verified on GitHub Actions (see [reliability.md](reliability.md)).
- **Would change if:** the rebuild took long enough to matter. The vintage logic would stay the same; only the materialization would change.

## 4. Revisions compared after rounding to the coarser precision

- **Chosen:** a new vintage starts only if the value differs from the last vintage kept after both are rounded to the larger of their two precisions (`10^(scalar_factor - decimals)`).
- **Alternatives:** compare raw numbers; compare with a fixed tolerance.
- **Why:** StatCan reports a value together with a scale factor (GDP in millions, retail in thousands) and a number of decimals, and series use different ones. If a release re-expressed the same number with another scale or fewer decimals, a raw comparison would count it as a revision, and a fixed tolerance would be wrong for some units. Rounding to what both releases could express handles each pair exactly. This case has not been seen in the real data so far; it is covered by a hand-built test (`test_scale_and_decimal_changes_are_not_revisions`).
- **Compared with the last kept vintage, not the previous observation:** with mixed precisions, comparing neighbours can miss a revision. 100.24, then 100.2 (one decimal: same), then 100.16 is a revision of 100.24, but 100.16 and 100.2 agree at one decimal. The first version compared neighbours; this was found in a review on 2026-11-07, reproduced by `test_mixed_precision_compares_with_last_kept_vintage` and fixed with a recursive CTE that carries the last kept value. On the real data the vintages were the same before and after the fix ([bug-log.md](bug-log.md), entry 5).

## 5. Growth rates, not levels, for the revision analysis

- **Chosen:** measure GDP revisions as changes in month-over-month growth (percentage points).
- **Alternative:** revisions of the level (chained dollars).
- **Why:** Statistics Canada changed the base year of chained dollars twice in the period (the 30 November 2018 and 30 November 2023 releases), which shifts every level at once. Level revisions mix that definitional change with real revisions. Growth rates are comparable across base years. First-release growth uses the previous month as it was known at the same release, so it does not peek at later data.

## 6. Open-source Evidence with an export step, and the publication boundary in the export

- **Chosen:** the open-source Evidence framework (40.1.8) built to a static site on GitHub Pages, reading a separate file written by `canecon-export`.
- **Alternatives:** Streamlit (needs a running server; free hosting sleeps); Evidence's newer hosted product (needs a login, cannot publish to Pages); pointing the dashboard straight at the warehouse.
- **Why:** a static site costs nothing, never sleeps, and can be opened without installing anything. The export step exists for two reasons. First, the dashboard bundles DuckDB 1.4, which cannot read files written by DuckDB 2.0 (see [bug-log.md](bug-log.md)), so the export writes storage format v1.4.0. Second, a static site ships its query results to every visitor, so hiding a series on a page is not enough. The export copies only series marked `public_dashboard = true` in `dbt/seeds/series_info.csv`, and `tests/test_export.py` checks that nothing else leaks. USD/CAD was held back because the Bank of Canada sources it from LSEG and its terms do not license third-party content for reuse; on 2026-11-07 it was dropped from collection altogether (see [sources.md](sources.md)).
- **Would change if:** the dashboard needed per-user interaction or private data. A server app would then be needed.

## 7. No Spark, Kafka or orchestration cluster

- **Chosen:** plain Python scripts, dbt and GitHub Actions cron.
- **Why:** seven series, one request batch a day, a 30-second build. Distributed tools would add setup and failure modes without solving any problem this data has. GitHub Actions gives scheduling, logs, failure e-mails and a free runner.
- **Would change if:** there were many sources with dependencies between them, or backfills that needed partial reruns. An orchestrator such as Dagster would then help; it is a possible later addition, still triggered by Actions.
