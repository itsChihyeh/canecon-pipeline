# CanEcon Vintage Pipeline

A scheduled Python + SQL pipeline that collects official Canadian economic data (Statistics Canada, Bank of Canada), keeps every published vintage, tracks revisions and lineage from raw API response to dashboard, and publishes a public dashboard.

**Status: P3 (reliability).** Daily collection, GDP vintage backfill, DuckDB + dbt models, catch-up for missed days, fault injection and data quality checks exist, with tests. The dashboard and the analysis do not yet.

## Question

How much do first-release estimates of Canada's monthly GDP and retail sales get revised, and how long until they settle?

## Planned design

- **raw** (append-only): every API response saved as-is with a manifest (source, URL and parameters, capture time in UTC, HTTP status, SHA-256).
- **vintages**: one row per new value of (series, reference period), with release time, first seen, superseded, and source snapshot.
- **marts**: latest value, first release, revision size, point-in-time views.

Stack: Python 3.12, DuckDB, dbt (dbt-duckdb), pytest, GitHub Actions, Evidence.

Data sources and their terms: [docs/sources.md](docs/sources.md).

## Run it

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12.

```bash
uv sync
uv run pytest -q
uv run canecon-collect --data-dir data/raw      # one daily capture
uv run canecon-backfill --data-dir data/raw     # one-time: official GDP vintages
uv run canecon-build --data-dir data/raw        # load into DuckDB, run dbt models, tests and quality checks
uv run canecon-catchup --data-dir data/raw      # fill missed collection days
uv run canecon-demo-failure                     # offline demo: injected 500s, retry, partial run, catch-up
```

Failure handling, catch-up, the quality checks and what was verified: [docs/reliability.md](docs/reliability.md).

Models and columns: [docs/data-dictionary.md](docs/data-dictionary.md).

The collector writes `objects/` (responses named by SHA-256), `manifest.jsonl` (one line per capture) and `runs.jsonl` (one line per run). Exit code is non-zero unless every request succeeded.

In GitHub Actions, `Daily collect` runs at 15:00 UTC, commits snapshots to the `data` branch, then builds the warehouse; the job fails (and GitHub emails the owner) if a request or an error-level quality check fails. Run it by hand with mode `catchup` to fill missed days. `CI` runs the tests on every push.

## Data attribution

Adapted from Statistics Canada data. This does not constitute an endorsement by Statistics Canada of this product. Bank of Canada data: source Bank of Canada; values may be transformed as described in the docs.
