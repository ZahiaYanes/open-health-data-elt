# ADR-002 — French numeric parsing and negative adjustments

- **Status**: Accepted
- **Date**: 2025-XX-XX
- **Context**: five dbt tests failed on the first full pipeline run

## Problem 1 — Silent data loss in numeric parsing

The source uses the full French numeric convention: dot as thousands separator,
comma as decimal separator (`632.831,40`). The initial conversion replaced only
the comma, producing invalid literals (`632.831.40`) coerced to NaN.

**Impact**: 475,177 reimbursed amounts (13.4%) and 541,250 base amounts (15.3%)
lost. Only values above EUR 1,000 were affected, which is why the issue did not
appear on the head sample.

**Fix**: strip the thousands separator before converting the decimal separator.

**Measured impact**: 13.4% of rows, but **96% of the monetary value**, because
the bug affected exactly the amounts above EUR 1,000. A missing-value rate alone
(13%) would have looked acceptable; only reconciling a *total* exposed the real
loss. This is the strongest argument for total-based reconciliation tests over
completeness ratios.

## Problem 2 — A reconciliation test that proved nothing

The first reconciliation test compared pipeline totals against a baseline
computed by **the same** parsing function. Both sides were wrong in the same
way, and `SUM()` ignores NULLs, so the test passed while 13% of the data was
missing.

**Fix**: the baseline is now computed by DuckDB reading the raw CSV
(`ingestion/compute_baseline.py`), sharing no code with the pandas ingestion
path, and stored as a versioned dbt seed. The test additionally compares
**non-null counts**, which totals alone cannot detect.

**Lesson**: a quality check that depends on the component it validates is not a
quality check.

## Problem 3 — Negative values are not errors

96 negative box counts, 175 negative reimbursed amounts and 102 negative base
amounts (< 0.01% of rows). These are accounting adjustments: cancellations,
corrections of previous periods, recovered overpayments.

**Decision**: values are preserved, the naive `>= 0` range tests are removed,
and a distribution test (`assert_adjustments_stay_marginal`) fails if
adjustments exceed 0.1% of rows - which would signal a parsing regression or a
change in publisher conventions.

## Consequence

The totals reported in ADR-001 were underestimated and are superseded by
`transform/seeds/seed_source_baseline.csv`.