-- ATC dimension: WHO Anatomical Therapeutic Chemical classification.
--
-- Grain: one row per distinct ATC path (level 1 to level 5).
-- The path, not the level-5 code alone, is the grain: level 5 is masked on 9.2%
-- of rows (ADR-001), and those rows still carry a meaningful level 1-4 path.
--
-- Dimensions are built on codes. Labels are descriptive attributes only,
-- because codes outnumber labels at every level (1,081 level-5 codes for
-- 1,022 labels): a label is not a key.

with paths as (

    select distinct
        atc_level_1,
        atc_level_2,
        atc_level_3,
        atc_level_4,
        atc_level_5,
        atc_level_1_label,
        atc_level_2_label,
        atc_level_3_label,
        atc_level_4_label,
        atc_level_5_label
    from {{ ref('stg_phmev__dispensing') }}

)

select
    {{ dbt_utils.generate_surrogate_key([
        'atc_level_1', 'atc_level_2', 'atc_level_3', 'atc_level_4', 'atc_level_5'
    ]) }} as atc_key,

    atc_level_1,
    atc_level_2,
    atc_level_3,
    atc_level_4,
    atc_level_5,

    atc_level_1_label,
    atc_level_2_label,
    atc_level_3_label,
    atc_level_4_label,
    atc_level_5_label,

    -- Deepest level actually disclosed for this path: lets downstream models
    -- state the resolution of an analysis instead of silently assuming it.
    case
        when atc_level_5 is not null then 5
        when atc_level_4 is not null then 4
        when atc_level_3 is not null then 3
        when atc_level_2 is not null then 2
        when atc_level_1 is not null then 1
        else 0
    end as disclosed_depth

from paths