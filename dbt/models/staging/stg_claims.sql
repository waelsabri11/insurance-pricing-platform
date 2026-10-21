-- One row per claim. The source has no claim id, so one is derived deterministically.
select
    row_number() over (order by "IDpol", "ClaimAmount") as claim_id,
    cast("IDpol" as bigint)                               as policy_id,
    cast("ClaimAmount" as double)                         as claim_amount
from {{ source('raw', 'freMTPL2sev') }}
