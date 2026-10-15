-- Prescribing facility dimension.
--
-- Grain: one row per facility identifier (etb_rgt).
-- This is the most reliable analysis axis in the source: 100% populated,
-- never masked (ADR-001).
--
-- The uniqueness test on facility_id is deliberately strict: if a facility
-- appears with diverging attributes (name, category, postal code), the test
-- fails and tells us the source carries slowly changing attributes that need
-- an explicit resolution rule. We let the test establish that fact rather
-- than assume it away with a silent DISTINCT ON.

with facilities as (

    select distinct
        facility_id,
        facility_name,
        facility_legal_name,
        facility_category_code,
        facility_category_group,
        postal_code,
        city_name,
        facility_region_code,
        facility_reports_age,
        facility_reports_sex
    from {{ ref('stg_phmev__dispensing') }}

)

select
    facility_id as facility_key,
    *
from facilities