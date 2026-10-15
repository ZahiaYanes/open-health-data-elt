-- Antimicrobial stewardship indicator.
--
-- Question: does the share of critical antibiotics among all systemic
-- antibacterials (ATC J01) differ across types of prescribing facility?
--
-- Critical antibiotics are those whose excessive use most strongly drives
-- bacterial resistance. Their relative share is a recognised prescribing
-- quality marker.
--
-- Methodological notes
-- --------------------
-- 1. The indicator is a ratio *within* ATC J01. Box counts are a weak unit
--    (a box of 6 tablets differs from a box of 90), but comparing antibiotics
--    to antibiotics keeps that bias largely cancelled out. Cross-class volume
--    comparisons are never made.
-- 2. Rows whose ATC level 4 is masked are excluded from the numerator logic and
--    counted separately, so the indicator is always reported together with the
--    share of data it could not classify.
-- 3. Dispensing fees carry no product and are excluded.
-- 4. No spend measure is used: this is a quality indicator, not a cost one.

with antibacterials as (

    select
        facts.facility_key,
        facts.reference_year,
        facts.n_boxes,
        atc.atc_level_4,
        atc.atc_level_5,
        atc.atc_level_4 is null as is_class_unresolved
    from {{ ref('fct_drug_dispensing') }} as facts
    inner join {{ ref('dim_atc') }} as atc
        on facts.atc_key = atc.atc_key
    where atc.atc_level_2 = 'J01'          -- systemic antibacterials
      and not facts.is_dispensing_fee

),

flagged as (

    select
        antibacterials.*,
        -- A row is critical when its ATC level 4 matches the reference list.
        critical.atc_code is not null as is_critical
    from antibacterials
    left join {{ ref('ref_critical_antibiotics') }} as critical
        on antibacterials.atc_level_4 = critical.atc_code
       and critical.atc_level = 4

),

by_facility_type as (

    select
        flagged.reference_year,
        facility.facility_category_group,

        count(distinct flagged.facility_key)                  as n_facilities,
        count(distinct flagged.atc_level_5)                   as n_distinct_substances,

        sum(flagged.n_boxes)                                  as n_boxes_j01,
        sum(case when flagged.is_critical
                 then flagged.n_boxes else 0 end)             as n_boxes_critical,
        sum(case when flagged.is_class_unresolved
                 then flagged.n_boxes else 0 end)             as n_boxes_unresolved_class

    from flagged
    inner join {{ ref('dim_facility') }} as facility
        on flagged.facility_key = facility.facility_key
    group by 1, 2

)

select
    reference_year,
    facility_category_group,
    n_facilities,
    n_distinct_substances,
    n_boxes_j01,
    n_boxes_critical,

    -- The indicator itself.
    round(100.0 * n_boxes_critical / nullif(n_boxes_j01, 0), 2)
        as critical_antibiotic_share_pct,

    -- Published alongside the indicator: the share of volume whose therapeutic
    -- class could not be resolved because the publisher masked it. Reading the
    -- indicator without this figure would be misleading.
    round(100.0 * n_boxes_unresolved_class / nullif(n_boxes_j01, 0), 2)
        as unresolved_class_share_pct

from by_facility_type
order by critical_antibiotic_share_pct desc