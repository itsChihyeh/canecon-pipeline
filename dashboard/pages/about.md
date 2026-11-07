---
sidebar_position: 4
title: About and sources
---

This dashboard is the output of [CanEcon Vintage Pipeline](https://github.com/itsChihyeh/canecon-pipeline), a
personal project. A scheduled GitHub Actions job collects official data every day, stores each raw API response
unchanged (named by its SHA-256) on the repository's `data` branch, rebuilds a DuckDB warehouse with dbt, runs
tests and data quality checks, and rebuilds this site. It is not an official product.

```sql build
select * from canecon.build_info
```

```sql sources
select s.label, s.definition, s.source_name, s.source_code, s.source_url,
       f.last_published_at
from canecon.series s join canecon.series_freshness f using (series_id)
order by s.source_name desc, s.label
```

Built <Value data={build} column=built_at fmt='yyyy-mm-dd H:MM' /> UTC from `data` branch commit <Value data={build} column=data_commit />.

## Series

<DataTable data={sources} rows=20>
  <Column id=label title="Series" />
  <Column id=definition wrap=true />
  <Column id=source_name title="Source" />
  <Column id=source_url title="Table / series" contentType=link linkLabel=source_code openInNewTab=true />
  <Column id=last_published_at title="Latest release used (UTC)" fmt='yyyy-mm-dd' />
</DataTable>

GDP revision history before 2026-10-30 comes from Statistics Canada Table 36-10-0491-01, *Historical (real-time)
releases of gross domestic product (GDP) at basic prices, by industry, monthly*
([link](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3610049101)).

## Attribution

Adapted from Statistics Canada, Table 36-10-0434-01 Gross domestic product (GDP) at basic prices, by industry,
monthly; Table 36-10-0491-01 Historical (real-time) releases of gross domestic product (GDP) at basic prices, by
industry, monthly; Table 20-10-0056-01 Monthly retail trade sales by province and territory; Table 14-10-0287-01
Labour force characteristics, monthly, seasonally adjusted and trend-cycle; Table 18-10-0004-01 Consumer Price
Index, monthly, not seasonally adjusted; reference dates as listed in the table above. This does not constitute
an endorsement by Statistics Canada of this product. Used under the
[Statistics Canada Open Licence](https://www.statcan.gc.ca/en/terms-conditions/open-licence).

Interest-rate data (target for the overnight rate, 2-year and 10-year benchmark bond yields): source
[Bank of Canada](https://www.bankofcanada.ca/terms/), via the Valet API. Values are shown as published, rounded
in charts and tables; growth and change figures are computed here. This site is not endorsed by the Bank of Canada.

The USD/CAD exchange rate is collected by the pipeline but not shown. The Bank of Canada notes that its exchange
rate data comes from LSEG, and its terms say third-party content is not licensed for reuse unless stated.

## How to read the numbers

- *Reference period*: the month (or day) a number describes. *Published*: when the source released it.
  *Captured*: when our collector received it. They are stored separately.
- Bank of Canada series have no release time in the API, so their *published* time is our capture time.
- Growth rates and 12-month changes are computed here from published levels.
- Revision history for series other than GDP starts with our first capture on 2026-11-07.
- Models and columns: [data dictionary](https://github.com/itsChihyeh/canecon-pipeline/blob/main/docs/data-dictionary.md).
  Failure handling and checks: [reliability](https://github.com/itsChihyeh/canecon-pipeline/blob/main/docs/reliability.md).
