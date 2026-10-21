-- Claim grain, with the rating attributes of the policy that produced it.
select
    c.claim_id,
    c.policy_id,
    c.claim_amount,
    p.driver_age_band,
    p.vehicle_age_band,
    p.bonus_malus_band,
    p.density_band,
    p.area_code,
    p.fuel_type,
    p.vehicle_brand,
    p.region_2016
from {{ ref('stg_claims') }} c
join {{ ref('fct_policies') }} p using (policy_id)
