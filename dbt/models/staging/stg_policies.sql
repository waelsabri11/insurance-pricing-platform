-- One row per policy-year. Renames to snake_case and fixes types; no business logic.
select
    cast("IDpol" as bigint)         as policy_id,
    cast("ClaimNb" as integer)      as claim_count,
    cast("Exposure" as double)      as exposure_years,
    cast("VehPower" as integer)     as vehicle_power,
    cast("VehAge" as integer)       as vehicle_age,
    cast("DrivAge" as integer)      as driver_age,
    cast("BonusMalus" as integer)   as bonus_malus,
    cast("VehBrand" as varchar)     as vehicle_brand,
    cast("VehGas" as varchar)       as fuel_type,
    cast("Area" as varchar)         as area_code,
    cast("Density" as integer)      as population_density,
    cast("Region" as varchar)       as region_name
from {{ source('raw', 'freMTPL2freq') }}
