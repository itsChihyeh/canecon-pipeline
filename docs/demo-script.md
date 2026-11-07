# Demo script

About 8 minutes. Part A needs only a browser. Part B needs a clone with `uv sync` done. Numbers below are from the `data` branch at `53f8060` (2026-11-07); the live dashboard is rebuilt daily, so they can move.

## A. Dashboard (browser, 3 minutes)

1. **Problem.** Open https://itschihyeh.github.io/canecon-pipeline/. "Official numbers change after they are published. Most data projects keep only the latest value; this pipeline keeps every published value, with when it was published, when we saw it, and the raw response it came from."
2. **A revision.** The home page opens with it, and *Revision explorer* lists its 18 vintages at the top (or pick series *Real GDP*, period *2021-07-01* in the explorer below). Growth for July 2021 was first published on 2021-10-01 as −0.06%, then −0.09% at the next release, +0.32% at the one after, and is +0.68% today: a reported decline became a clear increase.
3. **Lineage.** In the same table, click the raw snapshot link of a vintage. It opens the exact API response on the `data` branch, named by its SHA-256.
4. **No look-ahead.** Open *Point in time*, pick a month-end in 2021 or 2020. The table shows what was known on that day next to today's value. The same rule is `canecon.pit.as_of`: a vintage counts only if `valid_from <= T < valid_to`.
5. **Result.** Back on *Revision explorer*: across 140 months, first-release GDP growth moved 0.15 percentage points on average by today, and the first release had the right sign in 86% of months. Details and limits: [analysis.md](analysis.md).
6. **Health.** Open *Data quality*: 23 checks, one expected warning (GDP fell 10.7% in April 2020, a real event), collection days and runs.

## B. Terminal (5 minutes)

```bash
uv run --group orchestration --extra ai pytest -q   # 65 tests, about 2 minutes
uv run canecon-demo-failure      # offline: injected 500/503, retries, partial run, missing day, catch-up
```

In the demo output point at: the retry waits (2 s, 4 s, 8 s), `run status: partial (2/3 requests ok)`, `this run's data is not loaded`, the `missing_collection_days` warning, then `caught_up` after the catch-up.

Idempotency, if asked: two back-to-back runs on GitHub Actions added manifest lines but no new snapshot files, and the rebuilt `vintages` table was identical row by row ([reliability.md](reliability.md#idempotent-reruns-checked-on-github-actions)).

Build from the real snapshots (30–60 seconds after the fetch, mostly dbt start-up):

```bash
git fetch origin data && mkdir -p data/snap && git archive origin/data | tar -x -C data/snap
uv run canecon-build --data-dir data/snap/raw --db data/local/warehouse.duckdb
```

Expected: `dbt build: ok` and one quality warning, the April 2020 GDP drop.

## Questions to be ready for

- Reference period vs publication time vs capture time, with July 2021 GDP as the example.
- What happens in the tables when a value is revised: a new row in `vintages`, the old row gets `valid_to`.
- Why a rerun on the same day does not duplicate anything: same bytes, same SHA-256, same file.
- What the dashboard shows if half the requests fail: nothing from that run; the day is missing until catch-up.
- Why growth rates and not levels: two base-year changes.
