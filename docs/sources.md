# Data sources

All facts below were checked on **2026-11-07** against official APIs or pages. Re-check before relying on them.

## Series (first batch)

Statistics Canada values were confirmed with WDS `getSeriesInfoFromVector` / `getDataFromVectorsAndLatestNPeriods`. Bank of Canada values were confirmed with Valet `observations/.../json?recent=2`.

| Source | Table / code | Vector | Series | Freq | Scale | Latest seen 2026-11-07 |
|---|---|---|---|---|---|---|
| StatCan | 36-10-0434-01 | v65201210 | GDP at basic prices, all industries, SAAR, chained (2017) dollars | Monthly | millions (scalar 6) | 2026-08, released 2026-10-30 |
| StatCan | 20-10-0056-01 | v1446859483 | Retail trade, total retail sales, Canada, seasonally adjusted | Monthly | thousands (scalar 3) | 2026-08, released 2026-10-23 |
| StatCan | 14-10-0287-01 | v2062815 | Unemployment rate, 15+, total gender, SA | Monthly | units (%) | 2026-10, released 2026-11-06 |
| StatCan | 18-10-0004-01 | v41690973 | CPI, all-items, Canada (not SA) | Monthly | units (index) | 2026-09, released 2026-10-19 |
| BoC Valet | V39079 | – | Target for the overnight rate | Business daily | % | 2026-11-05 |
| BoC Valet | FXUSDCAD | – | USD/CAD daily average exchange rate | Business daily | CAD per USD | 2026-11-06 |
| BoC Valet | BD.CDN.2YR.DQ.YLD | – | Benchmark bond yield, 2-year | Business daily | % | 2026-11-05 |
| BoC Valet | BD.CDN.10YR.DQ.YLD | – | Benchmark bond yield, 10-year | Business daily | % | 2026-11-05 |

Change from the original plan: retail table **20-10-0008 is archived** (last period 2022-12; vector v52367097 stops there). It is replaced by **20-10-0056**.

Notes:
- WDS returns one `releaseTime` per vector release, applied to all returned points, not the time each point was first published. First-publication time per value therefore has to come from our own captures or from vintage tables.
- StatCan GDP mixes `scalarFactorCode` 6 with raw values like `2371635.0`; retail uses 3. Revision detection must compare values after applying scale and decimals.

## Can history be backfilled? (vintages)

Found by listing all WDS cubes (`getAllCubesListLite`) and filtering titles for "real-time" / "vintage".

| Series | Official vintage table | Status 2026-11-07 |
|---|---|---|
| Monthly GDP by industry | **36-10-0491** "Historical (real-time) releases of GDP at basic prices, by industry, monthly" | Current, last period 2026-07 |
| Retail trade | 20-10-0081 "Historical (real-time) releases of monthly retail trade, sales" | **Inactive**, last period 2025-12 |
| CPI (core measures only) | 18-10-0259 | Current; covers BoC core measures, not all-items |
| Unemployment rate | none found | – |
| BoC series | none found | Valet values are treated as final; we only record what we see |

Implication: GDP revision history can be backfilled from 36-10-0491. Retail can be backfilled only up to 2025-12; after that, retail revision history starts from our first capture date. Other series start from first capture. Structure of 36-10-0491 still needs to be inspected in P1.

## Terms and attribution

**Statistics Canada Open Licence** (https://www.statcan.gc.ca/en/terms-conditions/open-licence, page modified 2025-07-10). For value-added products the required wording is:

> Adapted from Statistics Canada, *name of product*, *reference date*. This does not constitute an endorsement by Statistics Canada of this product.

Do not use the Statistics Canada name or logo as branding.

**Bank of Canada Terms of Use** (https://www.bankofcanada.ca/terms/): content may be freely used with attribution to the Bank of Canada and an indication if changes were made. Exchange-rate data is noted as sourced from LSEG; the terms say third-party content is not licensed for reuse unless stated. Open question: whether this restricts republishing FXUSDCAD on a public dashboard. Until resolved, show FX only as derived charts with attribution, or drop it from the public dashboard.

## Rate limits and timing

- StatCan WDS (https://www.statcan.gc.ca/en/developers/wds/user-guide): 50 requests/s server-wide, 25 requests/s per IP. Data released business days at 8:30 ET. From midnight to 8:30 ET some methods return no data; tables being updated can return HTTP 409. Schedule the daily run after ~10:00 ET and treat 409 as retryable.
- Bank of Canada Valet: terms forbid circumventing request limits but no numeric limit was found (the docs page did not render for automated reading). One small request per day is far below any plausible limit.

## GDP backfill (done 2026-11-07)

36-10-0491 has a Release dimension with 140 members (March 3, 2015 to September 29, 2026). Coordinate `1.1.1.1.<release>` = Canada, SAAR, chained (2017) dollars, all industries. `canecon-backfill` fetches them in 8 requests and stores them as raw snapshots like any other capture. The points' own `releaseTime` is the table refresh time (2026-10-13 for every release), so the publication date comes from the Release member name, at 08:30 Eastern.

Finding: levels in this table jump when the base year changes (for 2015-01: about 1.66M before the Dec 2018 release, 1.81M after it, 1.91M from Dec 2023). These are definitional, not economic revisions, so revision analysis uses month-over-month growth (`mart_growth_revisions`), not levels.

Coverage assumption: the vintage table plus live captures cover every monthly GDP release since 2015-03 without gaps (table ends with the 2026-09-29 release; live capture starts with the 2026-10-30 release).

## Open items

- Confirm whether FX data may be republished.
- Read the WDS appendix on status/symbol codes (e.g. revised flags) and correction fields.
