"""
Independent reconciliation baseline.

Computes the source totals that the dbt pipeline must reproduce.

Why an independent implementation
---------------------------------
A baseline computed by the same code as the pipeline proves nothing: a parsing
bug affects both sides and the reconciliation test passes while data is lost.
This exact failure happened (see ADR-002).

This module therefore shares no code with the pandas ingestion path:
- it reads the file with the standard `csv` module, not pandas
- it parses numbers with `Decimal`, giving exact decimal arithmetic over 3.5M
  additions instead of accumulated floating-point error
- it counts unparsable values explicitly, instead of coercing them to NaN

The result is written as a dbt seed, making the baseline versioned and testable.

Author: Zahia Yanes
"""

import argparse
import csv
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

# --- Configuration ---

SEED_PATH = Path("transform/seeds/seed_source_baseline.csv")
ENCODING = "cp1252"
DELIMITER = ";"

# Source column -> baseline measure name
MEASURES = {"BOITES": "boxes", "REM": "reimbursed_eur", "BSE": "base_eur"}

# The source may hold very long rows; raise the csv field size limit.
csv.field_size_limit(sys.maxsize)


def parse_fr_decimal(value):
    """
    Parse a French-formatted number into an exact Decimal.

    French convention: dot as thousands separator, comma as decimal separator
    (e.g. "632.831,40"). Written independently from the ingestion module on
    purpose: if both used the same helper, a shared bug would stay invisible.

    Parameters
    ----------
    value : str
        Raw field value.

    Returns
    -------
    decimal.Decimal or None
        Parsed value, or None if the field cannot be parsed.
    """
    cleaned = value.strip().replace(".", "").replace(",", ".")
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def compute(path, year):
    """
    Stream the raw CSV and accumulate exact source totals.

    Parameters
    ----------
    path : pathlib.Path
        Path to the raw CSV file.
    year : int
        Reference year, stored alongside the totals.

    Returns
    -------
    dict
        Baseline row, ready to be written as a seed.
    """
    totals = {name: Decimal(0) for name in MEASURES.values()}
    negatives = {name: 0 for name in MEASURES.values()}
    unparsable = {name: 0 for name in MEASURES.values()}
    n_rows = 0

    with open(path, newline="", encoding=ENCODING) as handle:
        reader = csv.DictReader(handle, delimiter=DELIMITER)
        # Column names are inconsistently cased in the source (BOITES, rem...).
        reader.fieldnames = [name.strip().upper() for name in reader.fieldnames]

        for row in reader:
            n_rows += 1
            for column, name in MEASURES.items():
                parsed = parse_fr_decimal(row[column])
                if parsed is None:
                    unparsable[name] += 1
                    continue
                totals[name] += parsed
                if parsed < 0:
                    negatives[name] += 1

            if n_rows % 500_000 == 0:
                print(f"   {n_rows:>10,} rows read", end="\r")

    print(f"   {n_rows:>10,} rows read")

    # Any unparsable value means the baseline itself is unreliable: fail loudly
    # rather than publish a silently wrong reference.
    for name, count in unparsable.items():
        if count:
            raise ValueError(
                f"{count:,} unparsable values in '{name}': "
                "the French decimal convention is not what we assume."
            )

    return {
        "reference_year": year,
        "n_rows": n_rows,
        "total_boxes": int(totals["boxes"]),
        "total_reimbursed_eur": f'{totals["reimbursed_eur"]:.2f}',
        "total_base_eur": f'{totals["base_eur"]:.2f}',
        "n_negative_boxes": negatives["boxes"],
        "n_negative_reimbursed": negatives["reimbursed_eur"],
        "n_negative_base": negatives["base_eur"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute the reconciliation baseline.")
    parser.add_argument("--path", required=True, help="path to the raw CSV source")
    parser.add_argument("--year", required=True, type=int, help="reference year")
    args = parser.parse_args()

    print("Computing baseline (independent implementation, exact decimal arithmetic)...")
    baseline = compute(Path(args.path), args.year)

    SEED_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SEED_PATH, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(baseline))
        writer.writeheader()
        writer.writerow(baseline)

    print()
    for key, value in baseline.items():
        print(f"   {key:<24} {value}")
    print(f"\nBaseline written to {SEED_PATH}")