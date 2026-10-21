-- Exposure, claim frequency, severity and pure premium for every level of every rating
-- dimension (long format), plus a portfolio total row.
{% set dims = segment_dimensions() %}

with policies as (
    select * from {{ ref('fct_policies') }}
),

by_segment as (
    {% for dim in dims %}
    select
        '{{ dim }}'                    as dimension,
        cast({{ dim }} as varchar)     as segment,
        count(*)                       as policies,
        sum(exposure_years)            as exposure_years,
        sum(claim_count)               as claims,
        sum(incurred_amount)           as incurred_amount
    from policies
    group by 1, 2
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
    union all
    select 'portfolio', 'all', count(*), sum(exposure_years), sum(claim_count), sum(incurred_amount)
    from policies
)

select
    dimension,
    segment,
    policies,
    exposure_years,
    claims,
    incurred_amount,
    claims / exposure_years                          as claim_frequency,
    incurred_amount / nullif(claims, 0)              as avg_severity,
    incurred_amount / exposure_years                 as pure_premium,
    exposure_years / sum(exposure_years) over (partition by dimension) as exposure_share
from by_segment
