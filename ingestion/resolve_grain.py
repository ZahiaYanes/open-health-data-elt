"""
Grain and semantics resolver.

Answers the three questions left open by the full scan, before any staging
model is written:

1. Which column combination forms the real primary key of the fact table?
2. How much volume and spend do "dispensing fee" rows (atc1 = '0') represent?
3. Do the top_etb_age / top_etb_sexe flags explain the masked age / sexe values?

Like scan_source.py, the file is streamed in chunks so memory stays flat.

Author: Zahia Yanes
"""

import argparse
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

# --- Configuration ---

ENCODING = "cp1252"
DELIMITER = ";"
CHUNK_SIZE = 500_000

MEASURES = ["boites", "rem", "bse"]

# Masking sentinel used by the publisher (statistical disclosure control)
MASKED = {
    "atc4": "99999",
    "atc5": "9999999",
    "cip13": "9999999999999",
    "age": "99",
    "sexe": "9",
    "top_gen": "9",
}

# Out-of-scope rows: pharmacist dispensing fees, not a drug
DISPENSING_FEE_ATC1 = "0"

# Candidate primary keys, from the narrowest to the most complete
CANDIDATE_GRAINS = {
    "A | cip13 + etb + age + sexe": ["cip13", "etb_rgt", "age", "sexe"],
    "B | A + atc5": ["cip13", "atc5", "etb_rgt", "age", "sexe"],
    "C | B + top_gen + gen_num": ["cip13", "atc5", "top_gen", "gen_num", "etb_rgt", "age", "sexe"],
    "D | C + full ATC path": ["atc1", "atc2", "atc3", "atc4", "atc5", "cip13",
                              "top_gen", "gen_num", "etb_rgt", "age", "sexe"],
}


def to_numeric_fr(series):
    """
    Convert a French-formatted numeric string series to float.

    The source uses the full French convention: dot as thousands separator and
    comma as decimal separator (e.g. "632.831,40"). Replacing only the comma
    produces invalid literals such as "632.831.40", which silently become NaN.
    Measured impact of that bug: 13-15% of monetary values lost (ADR-002).

    Negative values are preserved: they are accounting adjustments
    (cancellations, recovered overpayments), not parsing errors.

    Parameters
    ----------
    series : pd.Series
        Raw string series.

    Returns
    -------
    pd.Series
        Float series, non-parsable values set to NaN.
    """
    normalised = (
        series.str.strip()
        .str.replace(".", "", regex=False)   # thousands separator, carries no value
        .str.replace(",", ".", regex=False)  # decimal separator -> SQL/Python format
    )
    return pd.to_numeric(normalised, errors="coerce")

def resolve(path):
    """
    Stream the source and accumulate the statistics needed to settle the grain.

    Parameters
    ----------
    path : pathlib.Path
        Path to the raw CSV file.

    Returns
    -------
    dict
        Accumulated statistics.
    """
    n_rows = 0
    key_hashes = {name: [] for name in CANDIDATE_GRAINS}
    fee_rows = 0
    fee_totals = {m: 0.0 for m in MEASURES}
    all_totals = {m: 0.0 for m in MEASURES}
    top_gen_counts = Counter()      # top_gen value -> row count
    sexe_by_flag = Counter()        # (top_etb_sexe, sexe is masked) -> row count
    age_by_flag = Counter()         # (top_etb_age, age is masked) -> row count

    reader = pd.read_csv(
        path, sep=DELIMITER, encoding=ENCODING, dtype=str,
        low_memory=False, chunksize=CHUNK_SIZE,
    )

    for i, chunk in enumerate(reader, start=1):
        chunk.columns = [c.strip().lower() for c in chunk.columns]
        n_rows += len(chunk)

        # --- Q1: candidate primary keys ---
        # Hashing keeps the uniqueness check cheap: 8 bytes per row, not N strings.
        for name, columns in CANDIDATE_GRAINS.items():
            key_hashes[name].append(
                pd.util.hash_pandas_object(chunk[columns], index=False).to_numpy()
            )

        # --- Q2: dispensing fees vs actual drugs ---
        is_fee = chunk["atc1"].str.strip() == DISPENSING_FEE_ATC1
        fee_rows += int(is_fee.sum())
        for measure in MEASURES:
            values = to_numeric_fr(chunk[measure])
            all_totals[measure] += float(values.sum())
            fee_totals[measure] += float(values[is_fee].sum())

        # --- Q3: do the restitution flags explain the masking? ---
        top_gen_counts.update(chunk["top_gen"].str.strip().tolist())
        sexe_by_flag.update(
            zip(chunk["top_etb_sexe"].str.strip(),
                chunk["sexe"].str.strip() == MASKED["sexe"])
        )
        age_by_flag.update(
            zip(chunk["top_etb_age"].str.strip(),
                chunk["age"].str.strip() == MASKED["age"])
        )

        print(f"   chunk {i:>3} | {n_rows:>10,} rows", end="\r")

    print()
    return {
        "n_rows": n_rows,
        "key_hashes": {k: np.concatenate(v) for k, v in key_hashes.items()},
        "fee_rows": fee_rows,
        "fee_totals": fee_totals,
        "all_totals": all_totals,
        "top_gen_counts": top_gen_counts,
        "sexe_by_flag": sexe_by_flag,
        "age_by_flag": age_by_flag,
    }


def report(stats):
    """
    Print the resolution results, ready to paste into the ADR.

    Parameters
    ----------
    stats : dict
        Output of resolve().
    """
    n_rows = stats["n_rows"]
    print("\n" + "=" * 100)
    print(f"GRAIN & SEMANTICS RESOLUTION | {n_rows:,} rows")
    print("=" * 100)

    # --- Q1 ---
    print("\n[Q1] Candidate primary keys")
    for name, hashes in stats["key_hashes"].items():
        unique = len(np.unique(hashes))
        status = "UNIQUE ✅" if unique == n_rows else f"{n_rows - unique:,} collisions ❌"
        print(f"   {name:<42} {unique:>12,} distinct   {status}")

    # --- Q2 ---
    print("\n[Q2] Dispensing fees (atc1 = '0') vs drugs")
    fee_share = stats["fee_rows"] / n_rows
    print(f"   rows: {stats['fee_rows']:,} ({fee_share:.2%} of file)")
    print(f"   {'measure':<12}{'total':>20}{'of which fees':>20}{'fee share':>12}")
    for measure in MEASURES:
        total = stats["all_totals"][measure]
        fees = stats["fee_totals"][measure]
        share = fees / total if total else 0
        print(f"   {measure:<12}{total:>20,.2f}{fees:>20,.2f}{share:>11.2%}")

    # --- Q3 ---
    print("\n[Q3] top_gen value distribution (semantics to confirm in the data dictionary)")
    for value, count in sorted(stats["top_gen_counts"].items()):
        print(f"   top_gen = {value!r:<6} {count:>12,}  ({count / n_rows:>6.2%})")

    print("\n[Q3] Does top_etb_sexe explain masked sexe?")
    print(f"   {'top_etb_sexe':<16}{'sexe masked':<14}{'rows':>14}")
    for (flag, masked), count in sorted(stats["sexe_by_flag"].items()):
        print(f"   {flag!r:<16}{str(masked):<14}{count:>14,}")

    print("\n[Q3] Does top_etb_age explain masked age?")
    print(f"   {'top_etb_age':<16}{'age masked':<14}{'rows':>14}")
    for (flag, masked), count in sorted(stats["age_by_flag"].items()):
        print(f"   {flag!r:<16}{str(masked):<14}{count:>14,}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Resolve grain and coding semantics.")
    parser.add_argument("--path", required=True, help="path to the raw CSV source")
    args = parser.parse_args()

    print("🔄 Resolving grain and semantics...")
    report(resolve(Path(args.path)))
    print("\n✅ Done — paste into docs/adr/ADR-001-source-phmev.md")