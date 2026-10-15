# ADR-003 — Hand-curated reference lists are SQL models, not seeds

- **Status**: Accepted
- **Date**: 2025-XX-XX

## Context

`seed_critical_antibiotics.csv` consistently failed to load through dbt-duckdb
with a CSV sniffing error, while DuckDB 1.1.3 read the exact same file without
error under every option set tested (`scripts/debug_seed_csv.py`). The failure
persisted after regenerating the file with the Python `csv` module and after
removing explicit `column_types`. It is a dbt-duckdb seed-loading issue, not a
file issue.

## Decision

Small, hand-curated reference lists are implemented as SQL models using a
`VALUES` clause, not as seeds.

## Consequences

- No dependency on CSV parsing in the critical path.
- The rationale for each entry lives next to the entry, reviewable in a pull
  request.
- Same tests, same documentation, same lineage as any other model.
- Seeds remain appropriate for machine-generated reference data
  (`seed_source_baseline`, produced by `ingestion/compute_baseline.py`).