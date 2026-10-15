-- Reconciliation test.
--
-- The pipeline must reproduce the totals measured directly on the raw CSV by
-- DuckDB (seed_source_baseline), a path that shares no parsing code with the
-- pandas ingestion module. This cross-engine check is what makes the test
-- meaningful: an earlier version compared the pipeline against a baseline
-- produced by the same buggy function and passed while 13% of monetary values
-- were being lost (ADR-002).
--
-- A row-count check is included because SUM() silently ignores NULLs: totals
-- alone cannot detect dropped values.

with actual as (

    select
        reference_year,
        count(*)                                    as n_rows,
        count(amount_reimbursed_eur)                as n_reimbursed_present,
        count(amount_base_eur)                      as n_base_present,
        sum(n_boxes)                                as total_boxes,
        round(sum(amount_reimbursed_eur), 2)        as total_reimbursed_eur,
        round(sum(amount_base_eur), 2)              as total_base_eur
    from {{ ref('stg_phmev__dispensing') }}
    group by 1

),

expected as (

    select * from {{ ref('seed_source_baseline') }}

)

select
    expected.reference_year,
    actual.n_rows,
    expected.n_rows                 as expected_n_rows,
    actual.total_reimbursed_eur,
    expected.total_reimbursed_eur   as expected_total_reimbursed_eur
from expected
left join actual using (reference_year)
where actual.n_rows              is distinct from expected.n_rows
   -- every row must carry a parsed measure: no silent NULL
   or actual.n_reimbursed_present is distinct from expected.n_rows
   or actual.n_base_present       is distinct from expected.n_rows
   or actual.total_boxes          is distinct from expected.total_boxes
   -- float tolerance on monetary sums
   or abs(actual.total_reimbursed_eur - expected.total_reimbursed_eur) > 0.01
   or abs(actual.total_base_eur       - expected.total_base_eur)       > 0.01