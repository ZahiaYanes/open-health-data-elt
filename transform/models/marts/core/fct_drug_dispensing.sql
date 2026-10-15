-- Fact table: drugs prescribed in hospitals, dispensed in community pharmacies.
--
-- Grain: unchanged from staging - one row per ATC path x product x generic
-- status x facility x age band x sex x year (validated unique, ADR-001).
--
-- Monetary measures are kept as quality sensors only: they are the only
-- continuous columns, hence the only ones able to expose a lost row through a
-- total. Health indicators downstream are built on volumes and therapeutic
-- classes, never on spend.

{{ config(materialized = 'table') }}

select
    dispensing_key,

    -- Foreign keys
    {{ dbt_utils.generate_surrogate_key([
        'atc_level_1', 'atc_level_2', 'atc_level_3', 'atc_level_4', 'atc_level_5'
    ]) }} as atc_key,
    facility_id as facility_key,

    -- Degenerate dimensions: low cardinality, kept inline
    reference_year,
    age_band,
    sex,
    cip13,
    generic_status_code,

    -- Measures
    n_boxes,
    amount_reimbursed_eur,
    amount_base_eur,

    -- Disclosure flags: downstream models must never aggregate over a
    -- non-random missingness pattern without acknowledging it (ADR-001).
    is_age_masked,
    is_sex_masked,
    is_product_masked,
    is_dispensing_fee

from {{ ref('stg_phmev__dispensing') }}