-- Every loaded series needs thresholds in seeds/series_catalog.csv.
select distinct o.series_id
from {{ ref('stg_observations') }} o
left join {{ ref('series_catalog') }} c using (series_id)
where c.series_id is null
