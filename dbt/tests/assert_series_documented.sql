-- Every series in the catalog needs a label, definition and source link for the dashboard.
select c.series_id
from {{ ref('series_catalog') }} c
left join {{ ref('series_info') }} i using (series_id)
where i.series_id is null or i.definition is null or i.source_url is null
