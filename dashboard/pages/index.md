---
title: Canadian economic data, every published version
---

```sql build
select built_at, data_commit, quality_checked_as_of from canecon.build_info
```

```sql latest
select l.*, s.label from canecon.latest l join canecon.series s using (series_id)
```

```sql gdp
select ref_period, value / 1e12 as gdp_trillions,
       100 * (value / lag(value) over (order by ref_period) - 1) as mom_growth_pct
from canecon.latest where series_id = 'gdp_all_industries' and ref_period >= '2015-01-01'
order by ref_period
```

```sql gdp_last
select * from ${gdp} order by ref_period desc limit 1
```

```sql retail
select ref_period, value / 1e9 as retail_billions from canecon.latest
where series_id = 'retail_sales_total_sa' order by ref_period
```

```sql unemployment
select ref_period, value as unemployment_rate from canecon.latest
where series_id = 'unemployment_rate_sa' order by ref_period
```

```sql cpi
select cur.ref_period, cur.value as cpi_index,
       100 * (cur.value / prev.value - 1) as cpi_yoy_pct
from canecon.latest cur
join canecon.latest prev
  on prev.series_id = cur.series_id and prev.ref_period = cur.ref_period - interval 12 month
where cur.series_id = 'cpi_all_items'
order by cur.ref_period
```

```sql cpi_last
select * from ${cpi} order by ref_period desc limit 1
```

```sql unemployment_last
select * from ${unemployment} order by ref_period desc limit 1
```

```sql rates
select ref_period, label, value as rate_pct from ${latest}
where series_id in ('policy_rate_target', 'gov_bond_yield_2y', 'gov_bond_yield_10y')
order by ref_period
```

```sql rates_last
select label, ref_period, value from ${latest}
where series_id in ('policy_rate_target', 'gov_bond_yield_2y', 'gov_bond_yield_10y')
qualify row_number() over (partition by series_id order by ref_period desc) = 1
order by label
```

```sql info_gdp
select * from canecon.series where series_id = 'gdp_all_industries'
```
```sql info_retail
select * from canecon.series where series_id = 'retail_sales_total_sa'
```
```sql info_unemployment
select * from canecon.series where series_id = 'unemployment_rate_sa'
```
```sql info_cpi
select * from canecon.series where series_id = 'cpi_all_items'
```
```sql info_policy
select * from canecon.series where series_id = 'policy_rate_target'
```
```sql info_2y
select * from canecon.series where series_id = 'gov_bond_yield_2y'
```
```sql info_10y
select * from canecon.series where series_id = 'gov_bond_yield_10y'
```

```sql jul2021
select released_at, growth_pct
from canecon.growth_revision_path
where series_id = 'gdp_all_industries' and ref_period = '2021-07-01'
order by release_number
```

```sql jul2021_ends
select
    max(case when release_number = 1 then growth_pct end) as first_pct,
    arg_max(growth_pct, release_number) as latest_pct,
    count(*) - 1 as later_releases
from canecon.growth_revision_path
where series_id = 'gdp_all_industries' and ref_period = '2021-07-01'
```

```sql gdp_revision_summary
select count(*) as months,
       avg(abs(growth_revision_pp)) as mean_abs_revision_pp,
       100 * avg(case when sign(first_growth_pct) = sign(latest_growth_pct) then 1 else 0 end) as same_sign_pct
from canecon.growth_revisions
where series_id = 'gdp_all_industries'
```

Official economic figures change after they are first published. This pipeline collects Statistics Canada
and Bank of Canada data every day and keeps **every published value**, with when it was published, when it
was captured and the raw API response it came from. It can answer what was known on any past day, and how far
first releases move.

## Example: Canada's GDP growth for July 2021

First published as <Value data={jul2021_ends} column=first_pct fmt='0.00"%"' />, a small decline. After <Value data={jul2021_ends} column=later_releases /> later GDP releases it stands at <Value data={jul2021_ends} column=latest_pct fmt='0.00"%"' />, a clear increase. A table that keeps only the latest value cannot show this.

<LineChart data={jul2021} x=released_at y=growth_pct step=true yAxisTitle="July 2021 m/m growth as published, %" yFmt='0.00' xAxisTitle="release date" />

<BigValue data={gdp_revision_summary} value=months title="GDP months compared" />
<BigValue data={gdp_revision_summary} value=mean_abs_revision_pp title="Mean revision, first release to now (pp)" fmt='0.00' />
<BigValue data={gdp_revision_summary} value=same_sign_pct title="First release had the right sign (%)" fmt='0' />

Explore any month in the [Revision explorer](/revisions), check what was known on a past date in
[Point in time](/as-of), see the [analysis](https://github.com/itsChihyeh/canecon-pipeline/blob/main/docs/analysis.md)
and its limits, or browse the [dbt models and lineage graph](https://itschihyeh.github.io/canecon-pipeline/dbt-docs/).
Code: [GitHub](https://github.com/itsChihyeh/canecon-pipeline).

## Latest figures

Rebuilt every day from the raw API responses the pipeline keeps.
Built <Value data={build} column=built_at fmt='yyyy-mm-dd H:MM' /> UTC.

<BigValue data={gdp_last} value=mom_growth_pct title="Real GDP, m/m growth (%)" fmt='0.00' comparisonTitle="" />
<BigValue data={unemployment_last} value=unemployment_rate title="Unemployment rate (%)" fmt='0.0' />
<BigValue data={cpi_last} value=cpi_yoy_pct title="CPI, 12-month change (%)" fmt='0.0' />

Reference months: GDP <Value data={gdp_last} column=ref_period fmt='mmm yyyy' />,
unemployment <Value data={unemployment_last} column=ref_period fmt='mmm yyyy' />,
CPI <Value data={cpi_last} column=ref_period fmt='mmm yyyy' />.
Growth rates are computed here from the published levels; they are not official headline figures.

### Real GDP

<LineChart data={gdp} x=ref_period y=gdp_trillions yMin=1.6 yAxisTitle="trillions of chained (2017) dollars, SAAR" yFmt='0.00' />

<SeriesNote data={info_gdp} note="Shown from 2015 at current (latest) estimates." />

### Real GDP, month-over-month growth

<BarChart data={gdp} x=ref_period y=mom_growth_pct yAxisTitle="percent" yFmt='0.0' />

<SeriesNote data={info_gdp} note="Growth = this month / previous month - 1, from the latest estimates." />

### Retail sales

<LineChart data={retail} x=ref_period y=retail_billions yAxisTitle="billions of dollars, SA" yFmt='0.0' />

<SeriesNote data={info_retail} note="The API serves the latest 36 months." />

### Unemployment rate

<LineChart data={unemployment} x=ref_period y=unemployment_rate yAxisTitle="percent" yFmt='0.0' />

<SeriesNote data={info_unemployment} note="The API serves the latest 36 months." />

### CPI inflation

<LineChart data={cpi} x=ref_period y=cpi_yoy_pct yAxisTitle="percent, 12-month change" yFmt='0.0' />

<SeriesNote data={info_cpi} note="12-month change = index / index 12 months earlier - 1, computed here." />

### Interest rates

<DataTable data={rates_last}>
  <Column id=label title="Series" />
  <Column id=ref_period title="Latest date" fmt='yyyy-mm-dd' />
  <Column id=value title="Percent" fmt='0.00' />
</DataTable>

<LineChart data={rates} x=ref_period y=rate_pct series=label yAxisTitle="percent" yFmt='0.00' />

Daily series cover the latest 30 business days the API serves; history grows as collection continues.

<SeriesNote data={info_policy} />
<SeriesNote data={info_2y} />
<SeriesNote data={info_10y} />

The USD/CAD exchange rate is not shown: the Bank of Canada sources it from LSEG, whose terms do not license it for reuse, so it is no longer collected.

<Attribution />
