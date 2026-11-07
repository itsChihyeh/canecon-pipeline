{{ config(tags=['quality']) }}
-- Any error-level data quality check fails the build (see mart_quality_checks).
select * from {{ ref('mart_quality_checks') }} where status = 'error'
