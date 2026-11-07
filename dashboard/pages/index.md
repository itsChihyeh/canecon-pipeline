---
title: Canadian macro overview
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

Latest official figures for Canada, rebuilt every day from the raw API responses the pipeline keeps.
Every value can be traced to the exact snapshot it came from (see [Revision explorer](/revisions)).
Built <Value data={build} column=built_at fmt='yyyy-mm-dd H:MM' /> UTC.

<BigValue data={gdp_last} value=mom_growth_pct title="Real GDP, m/m growth (%)" fmt='0.00' comparisonTitle="" />
<BigValue data={unemployment_last} value=unemployment_rate title="Unemployment rate (%)" fmt='0.0' />
<BigValue data={cpi_last} value=cpi_yoy_pct title="CPI, 12-month change (%)" fmt='0.0' />

Reference months: GDP <Value data={gdp_last} column=ref_period fmt='mmm yyyy' />,
unemployment <Value data={unemployment_last} column=ref_period fmt='mmm yyyy' />,
CPI <Value data={cpi_last} column=ref_period fmt='mmm yyyy' />.
Growth rates are computed here from the published levels; they are not official headline figures.

## Real GDP

<LineChart data={gdp} x=ref_period y=gdp_trillions yMin=1.6 yAxisTitle="trillions of chained (2017) dollars, SAAR" yFmt='0.00' />

<SeriesNote data={info_gdp} note="Shown from 2015 at current (latest) estimates." />

## Real GDP, month-over-month growth

<BarChart data={gdp} x=ref_period y=mom_growth_pct yAxisTitle="percent" yFmt='0.0' />

<SeriesNote data={info_gdp} note="Growth = this month / previous month - 1, from the latest estimates." />

## Retail sales

<LineChart data={retail} x=ref_period y=retail_billions yAxisTitle="billions of dollars, SA" yFmt='0.0' />

<SeriesNote data={info_retail} note="The API serves the latest 36 months." />

## Unemployment rate

<LineChart data={unemployment} x=ref_period y=unemployment_rate yAxisTitle="percent" yFmt='0.0' />

<SeriesNote data={info_unemployment} note="The API serves the latest 36 months." />

## CPI inflation

<LineChart data={cpi} x=ref_period y=cpi_yoy_pct yAxisTitle="percent, 12-month change" yFmt='0.0' />

<SeriesNote data={info_cpi} note="12-month change = index / index 12 months earlier - 1, computed here." />

## Interest rates

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

The USD/CAD exchange rate is collected but not shown: the Bank of Canada sources it from LSEG, and whether it may be republished here is still being checked.

<Attribution />
