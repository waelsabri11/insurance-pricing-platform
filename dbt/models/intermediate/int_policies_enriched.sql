-- Policies joined to their claims and to the region reference, plus the rating bands used
-- for reporting. Bands follow the usual freMTPL2 case-study groupings
-- (Noll, Salzmann & Wuthrich, 2018).
with policies as (
    select * from {{ ref('stg_policies') }}
),

claims as (
    select * from {{ ref('int_policy_claims') }}
),

regions as (
    select * from {{ ref('region_mapping') }}
)

select
    p.policy_id,
    p.exposure_years,
    p.claim_count,
    coalesce(c.incurred_amount, 0)    as incurred_amount,
    coalesce(c.max_claim_amount, 0)   as max_claim_amount,
    p.vehicle_power,
    p.vehicle_age,
    p.driver_age,
    p.bonus_malus,
    p.vehicle_brand,
    p.fuel_type,
    p.area_code,
    p.population_density,
    p.region_name,
    r.insee_code_pre2016,
    r.region_2016,
    case
        when p.driver_age < 21 then '18-20'
        when p.driver_age < 26 then '21-25'
        when p.driver_age < 31 then '26-30'
        when p.driver_age < 41 then '31-40'
        when p.driver_age < 51 then '41-50'
        when p.driver_age < 71 then '51-70'
        else '71+'
    end as driver_age_band,
    case
        when p.vehicle_age < 1 then '0'
        when p.vehicle_age <= 10 then '1-10'
        else '11+'
    end as vehicle_age_band,
    case
        when p.bonus_malus = 50 then '050 (max bonus)'
        when p.bonus_malus < 80 then '051-079'
        when p.bonus_malus < 100 then '080-099'
        when p.bonus_malus = 100 then '100 (entry)'
        else '101+ (malus)'
    end as bonus_malus_band,
    case
        when p.population_density < 100 then '0001-0099'
        when p.population_density < 500 then '0100-0499'
        when p.population_density < 2000 then '0500-1999'
        else '2000+'
    end as density_band
from policies p
left join claims c using (policy_id)
left join regions r using (region_name)
