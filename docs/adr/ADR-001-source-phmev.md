# ADR-001 — Open PHMEV as primary source

- **Status**: Accepted
- **Date**: 2025-XX-XX
- **Context**: first source of the Open Health Data ELT pipeline

## Decision

Use **Open PHMEV** (hospital-prescribed drugs dispensed in community pharmacies,
published by the French National Health Insurance) as the primary fact source.

## Source facts (measured, not assumed)

Established by `ingestion/profile_source.py`, `scan_source.py` and
`resolve_grain.py` on the full 3,534,234-row file.

| Property | Value |
|---|---|
| Rows | 3,534,234 |
| Columns | 31 |
| Encoding | **cp1252** (not latin-1: `\x92` right-quote artefacts) |
| Delimiter | `;` |
| Decimal separator | `,` (French) |
| Time column | **none** — the reference period is only in the filename |

### Grain

The primary key is the **full dimensional tuple**: atc1, atc2, atc3, atc4, atc5, cip13, top_gen, gen_num, etb_rgt, age, sexe

3,534,234 distinct combinations for 3,534,234 rows. Narrower candidate keys fail:
`cip13 + etb + age + sexe` yields 966,246 collisions, caused by masked `cip13`
values. `top_gen` and `gen_num` add no discriminating power (functionally
determined by `cip13`): they are product attributes, not analysis axes.

### Statistical disclosure control

The publisher masks non-disclosed values with sentinels rather than NULLs.

| Column | Sentinel | Masked share |
|---|---|---|
| `sexe` | `9` | 62.5% |
| `age` | `99` | 28.1% |
| `cip13` | `9999999999999` | 27.6% |
| `top_gen` | `9` | 27.6% |
| `atc5` | `9999999` | 9.2% |
| `atc4` | `99999` | 4.0% |
| `atc1`–`atc3` | — | 0.0% |

Masking operates at **two levels**, verified with zero violations:

1. **Facility opt-out** — when `top_etb_sexe = '0'` (resp. `top_etb_age = '0'`),
   the value is masked in 100% of rows (1,303,249 and 17,865 rows).
2. **Row-level small-cell suppression** — when the flag is `'1'`, the value is
   still masked in 40.6% (sex) and 27.7% (age) of rows.

Masking is therefore **not missing at random**: it correlates with the reporting
facility. Consequence: no imputation, and any aggregation on `age` or `sexe`
must explicitly exclude masked rows and report the remaining population.

### Out-of-scope rows

`atc1 = '0'` (`l_atc1 = 'Honoraires de dispensation'`) are pharmacist dispensing
fees, not drugs: 5,837 rows (0.17%), 0 boxes, EUR 419,478 reimbursed (0.09%).
Flagged as `is_dispensing_fee` and excluded from drug marts.

### Reference integrity

ATC codes outnumber ATC labels at every level (atc5: 1,081 codes / 1,022 labels):
dimensions are built on **codes**, labels are descriptive attributes only.

### Geographic coverage

`region_etb` holds 17 values: 12 metropolitan regions + 5 overseas regions
(1-digit codes). **Corsica (94) is absent** from the file.
`region_etb` is the region of the **prescribing facility**, not of the patient:
population-based rates are therefore not computable from this source alone.

### Reconciliation baseline

| Measure | Source total |
|---|---|
| `boites` | 306,537,393 |
| `rem` | EUR 12,508,778,299.18 |
| `bse` | EUR 13,284,791,745.73 |
| negative `boites` / `rem` / `bse` | 96 / 185 / 110 |

Global reimbursement rate: 94.2%.

Computed by `ingestion/compute_baseline.py` (standard `csv` module, exact
`Decimal` arithmetic), an implementation sharing no code with the pandas
ingestion path. Stored as a versioned dbt seed and enforced by
`assert_source_totals_reconcile`.

> An earlier version of this section reported EUR 480,359,506.53 - a figure
> underestimated by a factor of 26 due to the parsing bug described in ADR-002.

## Consequences

- Marts are built on the **facility** and **ATC** axes (100% / 90.8% available).
- No mart is built at `sexe` grain (37.5% available).
- `top_gen` values `0/1/4/B/C` are kept as **raw codes** pending the official
  data dictionary; they will be decoded via a dbt seed.
  
### Therapeutic perimeter

Open PHMEV covers drugs **dispensed in community pharmacies**. Intravenous,
hospital-administered agents are therefore structurally absent: glycopeptides
(ATC J01XA, vancomycin and teicoplanin) do not occur anywhere in the file.
Carbapenems (J01DH) are present but marginal (41,962 boxes, the lowest volume
among antibacterial classes), consistent with home-hospitalisation use.

Consequence: antimicrobial indicators built on this source cover community
dispensing only and cannot describe last-line intravenous antibiotic use.

## Open questions

- [ ] Does `2025` refer to the care year or the publication year?
- [ ] Official meaning of `top_gen` codes `0`, `1`, `4`, `B`, `C`.

## Columns dropped at ingestion

`nom_voie`, `numero_voie` — postal street address, no analytical value,
21.5% and 2.1% null. `code_postal` and `region_etb` are kept for geography.