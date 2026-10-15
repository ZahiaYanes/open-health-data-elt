-- Reference list of critical antibiotics.
--
-- Critical antibiotics are those whose excessive use most strongly drives
-- bacterial resistance. This list drives the antimicrobial stewardship
-- indicator in mart_critical_antibiotics.
--
-- Why a model and not a seed
-- --------------------------
-- The list is small and hand-curated. Keeping it as SQL puts the rationale for
-- every entry next to the entry itself, reviewable in a pull request, with no
-- dependency on CSV parsing.
--
-- Scope note
-- ----------
-- Open PHMEV only covers drugs dispensed in community pharmacies. Intravenous,
-- hospital-administered agents are kept in the list for completeness but
-- flagged `expected_in_community_pharmacy = false`, and excluded from the
-- reference-integrity test. Verified on the full file: J01XA glycopeptides
-- never occur in the source.
--
-- SOURCE STATUS: provisional. Every row must be checked against the official
-- ANSM critical antibiotics list before the indicator is published.

{{ config(materialized = 'table') }}

select *
from (
    values
        ('J01MA', 4, 'Fluoroquinolones',
         'oral_and_iv', true,
         'Broad resistance selection and collateral damage to commensal flora',
         'to_verify'),

        ('J01DD', 4, 'Third-generation cephalosporins',
         'mainly_iv', true,
         'Major driver of ESBL-producing Enterobacteriaceae',
         'to_verify'),

        ('J01DH', 4, 'Carbapenems',
         'iv', true,
         'Last-line agents with few therapeutic alternatives',
         'to_verify'),

        ('J01XA', 4, 'Glycopeptides',
         'iv_only', false,
         'Hospital-administered only, outside the community-pharmacy perimeter',
         'to_verify'),

        ('J01CR', 4, 'Penicillin combinations with beta-lactamase inhibitors',
         'oral_and_iv', true,
         'High resistance-selection pressure',
         'to_verify')

) as reference (
    atc_code,
    atc_level,
    antibiotic_class,
    route_of_administration,
    expected_in_community_pharmacy,
    rationale,
    source_status
)