# Extensions: monthly brief, revision baseline, Dagster

Three optional additions on top of the core pipeline. None of them is needed by collection, the warehouse or the dashboard, and each fails without affecting them.

## 1. Monthly brief with a number check (`canecon-brief`, `src/canecon/brief.py`)

A language model writes a short English paragraph about one month; the program checks every number before anything is published.

1. **Facts.** For reference month M, as known at time T, `month_facts` computes up to 12 numbers from point-in-time vintages (`canecon.pit.as_of`, so nothing published after T is used): GDP and retail sales month-over-month growth, the unemployment rate and its change, CPI year-over-year and month-over-month, and the last value of the month and its change for the policy rate and the 2- and 10-year yields. Each fact has a fixed number of decimals. USD/CAD is not used (not cleared for publication).
2. **Citations.** The model must write every number as `[[series_id|YYYY-MM|measure|value]]`, copying the value exactly.
3. **Check.** `verify` looks up the fact for that same series, period and measure and requires the same digits. Any other number in the text, except a four-digit year, fails the brief. A check that only asks "does this number appear somewhere in the data" would pass 0.5% for retail sales when 0.5% is GDP's figure; `tests/test_brief.py` has that case.
4. **Retry, then fall back.** On failure the model gets one retry with the list of problems. If the retry fails too, or the API errors, the model's text is dropped and a fixed template built only from the facts is used instead. Each result is saved as JSON with every draft and the problems found.

Status (2026-11-07): the check, the retry and the fallback are tested with a scripted stand-in for the model (16 tests in `tests/test_brief.py`, all values hand-computed). **No language model has been called yet**, so there is no measured pass rate. Calling one needs an API key, which costs money and is the owner's decision. Until then `canecon-brief` without `--model` writes the template only:

```bash
uv run canecon-brief --month 2026-08                       # template only, no API call
uv run canecon-brief --month 2024-01:2026-10 --model <id>   # needs ANTHROPIC_API_KEY and the anthropic package
```

Limits:
- The check covers numbers, not wording: a draft that says "fell" next to a positive number passes. Direction words are not checked.
- For months before 2026-11-07, only GDP has a real point-in-time history. Other series' history before that date is today's data, so a brief for an older month uses current values for them.
- Daily series have about 30 recent observations in the data (from late September 2026), so their month-end values exist for September and October 2026 and their monthly change for October only.

## 2. Revision direction baseline (`canecon-baseline`, `src/canecon/baseline.py`)

Question: from what is known at a month's first release, can we tell whether its GDP growth will be revised up?

- Target: `growth_revision_pp > 0` in `mart_growth_revisions` (first release to today).
- Features known at the first release: first-release growth, and how far the previous month's growth had already moved by then (`mart_growth_revision_path`).
- Model: scikit-learn logistic regression, compared with "always up" and the training set's majority class.
- Walk-forward: month M is predicted by a model fit only on months first released at least 36 months before M (a month's revision is not known until later releases are out). Months released less than 36 months before the latest release are not scored. `tests/test_baseline.py` checks the embargo with a hand-worked calendar.

Result on `data` commit `53f8060` (run 2026-11-07, `uv run canecon-baseline`):

| Embargo | Months scored | Logistic regression | Always up | Majority class |
|---:|---:|---:|---:|---:|
| 36 months (default) | 44 (2020-01 to 2023-08) | 63.6% (28) | 52.3% (23) | 50.0% |
| 24 months | 69 (2018-12 to 2024-08) | 55.1% | 55.1% | 47.8% |
| 48 months | 21 (2020-12 to 2022-08) | 71.4% | 52.4% | 47.6% |

Reading: with the default embargo the model is right in 5 more months out of 44 than "always up". That gap is not robust: with a 24-month embargo it disappears, and the samples are small and include 2020. **There is no reliable evidence that the direction of revisions can be predicted from these features.** This stays a baseline for comparison, not a result to quote.

Limits: training labels use today's revisions, which were not all known at the time of each prediction; only one series; two features.

## 3. Dagster assets (`src/canecon/orchestration.py`)

The same steps as Dagster software-defined assets, for lineage, run history and checks in Dagster's UI:

```
raw_snapshots (external, written by the GitHub Actions collector)
  -> warehouse         canecon.build in its own process (dbt keeps its DuckDB connection open)
       [asset check] quality_checks: reads mart_quality_checks; fails on any error row
  -> dashboard_export  public series only
  -> monthly_brief     last complete month; template unless a model is configured
```

GitHub Actions still runs the daily collection and the dashboard. Dagster is not deployed anywhere; it is run locally:

```bash
uv sync --group orchestration
uv run --group orchestration dagster dev -m canecon.orchestration
```

Error-level quality checks already fail the dbt build, so after a successful build the asset check mostly shows the warnings. Tests (`tests/test_orchestration.py`, 3 tests): a build that fails on quality errors and a build with no snapshots both stop all downstream assets and write no files; the check passes with warnings and fails on an error row. The tests skip when Dagster is not installed; CI installs it.

Run by hand on `data` commit `53f8060` (2026-11-07, Dagster 1.13.29, in-process `materialize`): all four assets and the check succeeded in about 66 s, the check passed with 1 warning (the April 2020 GDP drop), and the brief for 2026-10 fell back to the template because no model was configured.

## Not done

- Terraform and cloud storage: needs a cloud account with billing; not started.
- A real language model run and its measured pass rate: waiting for the owner's decision on API cost.
