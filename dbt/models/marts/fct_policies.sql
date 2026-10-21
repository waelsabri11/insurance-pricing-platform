-- Policy grain: exposure, claims and incurred losses with rating attributes.
select * from {{ ref('int_policies_enriched') }}
