-- Staging model for Open PHMEV.
--
-- Grain: one row per
--   atc1-5 x cip13 x generic status x facility x age band x sex x year
-- Validated as unique on the full 3.5M-row file (see ADR-001).
--
-- This model turns the faithful landing copy into analysable data:
--   1. publisher sentinels -> NULL  (statistical disclosure control)
--   2. coded dimensions    -> explicit labels
--   3. out-of-scope rows   -> flagged, not deleted
--   4. a surrogate key is generated for testability
--
-- Sentinel convention observed in the source:
--   all-zeros  = dispensing fee, not a drug
--   all-nines  = value masked by the publisher

with source as (

    select * from {{ source('phmev', 'dispensing') }}

),

cleaned as (

    select
        -- Surrogate key, built on the raw tuple validated as unique in ADR-001.
        {{ dbt_utils.generate_surrogate_key([
            'atc_level_1', 'atc_level_2', 'atc_level_3', 'atc_level_4', 'atc_level_5',
            'cip13', 'generic_status_code', 'generic_group_id',
            'facility_id', 'age_band_code', 'sex_code', 'reference_year'
        ]) }} as dispensing_key,

        -- ----------------------------------------------------------------
        -- Therapeutic classification (WHO ATC)
        -- Codes drive the model; labels are descriptive only, because codes
        -- outnumber labels at every level (ADR-001).
        -- ----------------------------------------------------------------
        nullif(nullif(trim(atc_level_1), '9'),       '0')       as atc_level_1,
        nullif(nullif(trim(atc_level_2), '999'),     '000')     as atc_level_2,
        nullif(nullif(trim(atc_level_3), '9999'),    '0000')    as atc_level_3,
        nullif(nullif(trim(atc_level_4), '99999'),   '00000')   as atc_level_4,
        nullif(nullif(trim(atc_level_5), '9999999'), '0000000') as atc_level_5,

        atc_level_1_label,
        atc_level_2_label,
        atc_level_3_label,
        atc_level_4_label,
        atc_level_5_label,

        -- ----------------------------------------------------------------
        -- Product
        -- ----------------------------------------------------------------
        nullif(trim(cip13), '9999999999999')                    as cip13,
        product_label,

        -- Raw code kept undecoded on purpose: the official meaning of
        -- values 0 / 1 / 4 / B / C is not documented yet (ADR-001).
        nullif(trim(generic_status_code), '9')                  as generic_status_code,
        nullif(trim(generic_group_id), '9999')                  as generic_group_id,

        -- ----------------------------------------------------------------
        -- Patient profile
        -- ----------------------------------------------------------------
        case trim(age_band_code)
            when '0'  then '0-19'
            when '20' then '20-59'
            when '60' then '60+'
        end                                                     as age_band,

        case trim(sex_code)
            when '1' then 'M'
            when '2' then 'F'
        end                                                     as sex,

        -- ----------------------------------------------------------------
        -- Prescribing facility (100% populated, the most reliable axis)
        -- ----------------------------------------------------------------
        trim(facility_id)                                       as facility_id,
        facility_name,
        facility_legal_name,
        trim(facility_category_code)                            as facility_category_code,
        trim(facility_category_group)                           as facility_category_group,
        trim(postal_code)                                       as postal_code,
        city_name,
        -- Overseas regions use 1-digit codes in the source: padded to the
        -- 2-digit official INSEE format.
        lpad(trim(facility_region_code), 2, '0')                as facility_region_code,

        -- ----------------------------------------------------------------
        -- Disclosure-control flags
        -- When a flag is '0', the matching value is masked in 100% of rows.
        -- ----------------------------------------------------------------
        trim(facility_reports_age) = '1'                        as facility_reports_age,
        trim(facility_reports_sex) = '1'                        as facility_reports_sex,

        -- Explicit masking flags, so downstream models never silently
        -- aggregate over a non-random missingness pattern.
        trim(age_band_code) = '99'                              as is_age_masked,
        trim(sex_code) = '9'                                    as is_sex_masked,
        trim(cip13) = '9999999999999'                           as is_product_masked,

        -- Pharmacist dispensing fees: 0.17% of rows, 0 boxes, not a drug.
        -- Flagged rather than deleted, and excluded in the marts.
        trim(atc_level_1) = '0'                                 as is_dispensing_fee,

        -- ----------------------------------------------------------------
        -- Measures
        -- ----------------------------------------------------------------
        cast(n_boxes as bigint)                                 as n_boxes,
        cast(amount_reimbursed_eur as double)                   as amount_reimbursed_eur,
        cast(amount_base_eur as double)                         as amount_base_eur,

        -- ----------------------------------------------------------------
        -- Technical
        -- ----------------------------------------------------------------
        cast(reference_year as integer)                         as reference_year,
        _source_file,
        _ingested_at

    from source

)

select * from cleaned