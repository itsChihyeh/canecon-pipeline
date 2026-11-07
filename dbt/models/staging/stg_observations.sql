-- Typed observations with values on a common scale.
-- StatCan reports values in units of 10^scalar_factor (e.g. 6 = millions) with a
-- given number of decimals. value_scaled is the value in base units; precision_step
-- is the smallest difference the source can express at that precision.
select
    series_id,
    source_kind,
    ref_period,
    value as value_reported,
    scalar_factor,
    decimals,
    cast(value * cast(power(10, scalar_factor) as decimal(38, 10)) as decimal(38, 10)) as value_scaled,
    cast(power(10, scalar_factor - decimals) as decimal(38, 10)) as precision_step,
    published_at,
    captured_at,
    release_label,
    status_code,
    symbol_code,
    run_id,
    content_sha256 as source_snapshot_sha256,
    object_path as source_object_path
from {{ source('raw', 'observations') }}
