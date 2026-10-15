-- Reference-list integrity, scoped to the source perimeter.
--
-- Every reference code expected to be dispensed in community pharmacies must
-- occur in the data. A missing code would be a typo, an obsolete WHO code or a
-- level mismatch, and would silently understate the indicator.
--
-- Codes flagged `expected_in_community_pharmacy = false` are deliberately kept
-- in the reference list but excluded from this check: they are intravenous
-- hospital-only agents, outside the scope of Open PHMEV by construction.
-- Example: J01XA glycopeptides, verified absent from the full file.

with expected as (

    select atc_code
    from {{ ref('ref_critical_antibiotics') }}
    where atc_level = 4
      -- Boolean column: no comparison to 'yes' needed, unlike the former CSV seed.
      and expected_in_community_pharmacy

),

observed as (

    select distinct atc_level_4 as atc_code
    from {{ ref('dim_atc') }}
    where atc_level_4 is not null

)

select expected.atc_code
from expected
left join observed using (atc_code)
where observed.atc_code is null