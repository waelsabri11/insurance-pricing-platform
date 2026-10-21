-- ClaimNb in the policy file must equal the number of claim records in the severity file.
-- (The OpenML snapshot of freMTPL2 has a few mismatches; the CASdatasets one has none.)
select policy_id, claim_count, coalesce(c.claim_records, 0) as claim_records
from {{ ref('stg_policies') }}
left join {{ ref('int_policy_claims') }} c using (policy_id)
where claim_count <> coalesce(c.claim_records, 0)
