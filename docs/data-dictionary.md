# Data dictionary

Times are UTC. Three times are kept apart everywhere:

- **ref_period**: the period a number describes (first day of the month for monthly series, the date for daily series).
- **published_at / valid_from**: when the source published that value.
- **captured_at / first_seen_at**: when our collector received it.

## raw (rebuilt from the append-only snapshot store by `canecon.load`)

| Table | Grain | Notes |
|---|---|---|
| `raw.observations` | snapshot x series x ref_period | Parsed from successful runs only. `value` as reported, with `scalar_factor` (power of 10) and `decimals`. `content_sha256` / `object_path` point to the raw response. |
| `raw.captures` | request attempt | Copy of `manifest.jsonl`. |
| `raw.runs` | collector run | Copy of `runs.jsonl`; `status` is success / partial / failed. |

## staging

`stg_observations`: typed observations. `value_scaled = value x 10^scalar_factor` (base units). `precision_step = 10^(scalar_factor - decimals)`, the smallest change the source can express.

## vintages

`vintages`: one row per distinct published value of (series_id, ref_period).

| Column | Meaning |
|---|---|
| `vintage_number` | 1 = first value we have, 2 = first revision, ... |
| `value` | value in base units |
| `valid_from` / `valid_to` | publication time of this vintage / of the next one (null = current) |
| `first_seen_at` | capture time of the snapshot where we first saw this vintage |
| `revision_from_previous` | `value - previous vintage value` |
| `source_kind` | `statcan_live`, `statcan_realtime_table` (official vintage table) or `boc_live` |
| `source_snapshot_sha256`, `source_object_path` | lineage to the raw response |
| `observed_from` | earliest time we can vouch for the value (publication time for official vintage tables, capture time for live data) |

A new vintage starts only if the value differs from the previous one after rounding both to the coarser precision, so changes in scale factor or decimals are not revisions.

## marts

| Model | Question it answers |
|---|---|
| `mart_latest` | What is the current value? |
| `mart_first_release` | What was first published? `is_true_first_release` is false when the value was already out before our coverage of that series started. |
| `mart_revisions` | How much did the level move? Includes base-year changes; do not use for analysis. |
| `mart_growth_revisions` | How much was month-over-month growth revised (percentage points)? First growth uses the previous month as known at the same time. |
| `mart_data_freshness` | When did each request last succeed? |

## Point-in-time

`canecon.pit.as_of(con, T)` returns, for every series and period, the vintage with `valid_from <= T < valid_to`. Nothing published after T is used.
