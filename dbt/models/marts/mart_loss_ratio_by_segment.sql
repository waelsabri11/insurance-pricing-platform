{{ config(tags=['post_model']) }}
-- Loss ratio = incurred / technical premium on the held-out test policies, for three tariffs:
-- a flat rate (portfolio average pure premium), the GLM and the GBM. The dataset carries no
-- written premium, so "premium" here is each model's pure premium for the policy's exposure.
-- A well-segmented tariff keeps every segment close to 1.0.
{% set dims = segment_dimensions() %}

with scored as (
    select p.*, pr.premium_flat, pr.premium_glm, pr.premium_gbm
    from {{ ref('fct_policies') }} p
    join {{ source('model_outputs', 'policy_predictions') }} pr using (policy_id)
    where pr.split = 'test'
),

by_segment as (
    {% for dim in dims %}
    select
        '{{ dim }}'                    as dimension,
        cast({{ dim }} as varchar)     as segment,
        sum(exposure_years)            as exposure_years,
        sum(claim_count)               as claims,
        sum(incurred_amount)           as incurred_amount,
        sum(premium_flat)              as premium_flat,
        sum(premium_glm)               as premium_glm,
        sum(premium_gbm)               as premium_gbm
    from scored
    group by 1, 2
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
)

select
    *,
    incurred_amount / premium_flat as loss_ratio_flat,
    incurred_amount / premium_glm  as loss_ratio_glm,
    incurred_amount / premium_gbm  as loss_ratio_gbm
from by_segment
