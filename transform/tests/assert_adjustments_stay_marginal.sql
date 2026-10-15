-- Negative measures are legitimate accounting adjustments (cancellations,
-- corrections of previous periods, recovered overpayments) and are therefore
-- kept, not filtered out (ADR-002).
--
-- They must however stay marginal: a sudden rise would signal a parsing
-- regression or a change in the publisher's conventions.
--
-- Observed baseline on the 2025 file (3,534,234 rows):
--   96 negative box counts, 185 negative reimbursed amounts,
--   110 negative base amounts - i.e. about 0.005% of rows.
-- The test fails above 0.1%, leaving a wide margin for legitimate variation
-- while still catching an order-of-magnitude shift.

with adjustments as (

    select
        reference_year,
        count(*)                                                    as n_rows,
        sum(case when n_boxes < 0 then 1 else 0 end)                as n_negative_boxes,
        sum(case when amount_reimbursed_eur < 0 then 1 else 0 end)  as n_negative_reimbursed,
        sum(case when amount_base_eur < 0 then 1 else 0 end)        as n_negative_base
    from {{ ref('stg_phmev__dispensing') }}
    group by 1

)

select *
from adjustments
where n_negative_boxes      > n_rows * 0.001
   or n_negative_reimbursed > n_rows * 0.001
   or n_negative_base       > n_rows * 0.001