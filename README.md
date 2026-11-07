# CanEcon Vintage Pipeline

A scheduled Python + SQL pipeline that collects official Canadian economic data (Statistics Canada, Bank of Canada), keeps every published vintage, tracks revisions and lineage from raw API response to dashboard, and publishes a public dashboard.

**Status: P1 (daily collection).** The raw collector and its tests exist; modeling, dashboard and metrics do not yet. Nothing below is a measured result.

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
uv run canecon-collect --data-dir data/raw
```

The collector writes `objects/` (responses named by SHA-256), `manifest.jsonl` (one line per capture) and `runs.jsonl` (one line per run). Exit code is non-zero unless every request succeeded.

In GitHub Actions, `Daily collect` runs at 15:00 UTC and commits snapshots to the `data` branch. `CI` runs the tests on every push.

## Data attribution

Adapted from Statistics Canada data. This does not constitute an endorsement by Statistics Canada of this product. Bank of Canada data: source Bank of Canada; values may be transformed as described in the docs.
