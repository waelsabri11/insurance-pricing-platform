-- Claims rolled up to policy level.
select
    policy_id,
    count(*)            as claim_records,
    sum(claim_amount)   as incurred_amount,
    max(claim_amount)   as max_claim_amount
from {{ ref('stg_claims') }}
group by policy_id
