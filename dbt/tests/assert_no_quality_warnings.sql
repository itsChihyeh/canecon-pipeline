{{ config(tags=['quality'], severity='warn') }}
-- Warn-level checks are reported but do not fail the build (see mart_quality_checks).
select * from {{ ref('mart_quality_checks') }} where status = 'warn'
