"""
Full-scan source profiler.

Complements profile_source.py, which only reads the head of the file.
Because Open PHMEV is sorted by ATC class, a head sample is NOT representative:
value domains observed on the first rows are wrong. This script streams the
whole file in chunks (constant memory) to establish the facts the staging
model and the dbt tests will be written against.

What it reports:
- True row count
- True value domain of every low-cardinality column
- Share of "non restitue" sentinel values per column (statistical disclosure control)
- Grain validation: is the candidate primary key unique?
- Source totals, reused later as a dbt reconciliation test

Author: Zahia Yanes
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

# --- Configuration ---

ENCODING = "cp1252"          # confirmed by \x92 artefacts, latin-1 is wrong
DELIMITER = ";"
CHUNK_SIZE = 500_000         # rows per chunk, keeps memory flat
MAX_DISTINCT_TRACKED = 2_000  # above this, a column is high-cardinality: stop collecting

# Sentinel values used by the publisher to mask non-disclosed information
SENTINELS = {
    "atc4": "99999",
    "atc5": "9999999",
    "cip13": "9999999999999",
    "age": "99",
    "sexe": "9",
    "top_gen": "9",
    "gen_num": "9999",
}

# Candidate primary key to validate
CANDIDATE_GRAIN = ["cip13", "etb_rgt", "age", "sexe"]

# Measures to total, for later pipeline reconciliation
MEASURES = ["boites", "rem", "bse"]


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


def scan(path):
    """
    Stream the whole source file and accumulate structural statistics.

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
    nulls = {}            # column -> null count
    sentinel_hits = {}    # column -> sentinel count
    domains = {}          # column -> set of distinct values (or None if high-cardinality)
    totals = {m: 0.0 for m in MEASURES}
    key_hashes = []       # 64-bit hash of the candidate key, for uniqueness check

    reader = pd.read_csv(
        path,
        sep=DELIMITER,
        encoding=ENCODING,
        dtype=str,
        low_memory=False,
        chunksize=CHUNK_SIZE,
    )

    for i, chunk in enumerate(reader, start=1):
        # Column names are inconsistently cased in the source (atc1, L_ATC2, CIP13)
        chunk.columns = [c.strip().lower() for c in chunk.columns]
        n_rows += len(chunk)

        for column in chunk.columns:
            series = chunk[column]

            nulls[column] = nulls.get(column, 0) + int(series.isna().sum())

            if column in SENTINELS:
                hits = int((series.str.strip() == SENTINELS[column]).sum())
                sentinel_hits[column] = sentinel_hits.get(column, 0) + hits

            # Collect distinct values until the column proves high-cardinality
            if domains.get(column, set()) is not None:
                known = domains.setdefault(column, set())
                known.update(series.dropna().unique().tolist())
                if len(known) > MAX_DISTINCT_TRACKED:
                    domains[column] = None  # give up: not a coded dimension

        for measure in MEASURES:
            totals[measure] += float(to_numeric_fr(chunk[measure]).sum())

        # Hashing keeps the uniqueness check cheap: 8 bytes per row instead of 4 strings
        key_hashes.append(
            pd.util.hash_pandas_object(chunk[CANDIDATE_GRAIN], index=False).to_numpy()
        )

        print(f"   chunk {i:>3} | {n_rows:>10,} rows scanned", end="\r")

    print()
    return {
        "n_rows": n_rows,
        "nulls": nulls,
        "sentinel_hits": sentinel_hits,
        "domains": domains,
        "totals": totals,
        "key_hashes": np.concatenate(key_hashes),
    }


def report(stats):
    """
    Print the scan results in a form ready to paste into an ADR.

    Parameters
    ----------
    stats : dict
        Output of scan().
    """
    n_rows = stats["n_rows"]

    print("\n" + "=" * 100)
    print(f"FULL SCAN REPORT | {n_rows:,} rows")
    print("=" * 100)

    # --- Value domains ---
    print("\nValue domains (coded dimensions only):")
    for column, values in stats["domains"].items():
        if values is None:
            print(f"   {column:<22} HIGH CARDINALITY (> {MAX_DISTINCT_TRACKED:,} distinct)")
        elif len(values) <= 30:
            print(f"   {column:<22} {len(values):>4} values  {sorted(values)}")
        else:
            print(f"   {column:<22} {len(values):>4} values  (sample: {sorted(values)[:5]})")

    # --- Missingness: true nulls vs masked values ---
    print("\nMissingness (true NULL vs publisher sentinel):")
    print(f"   {'column':<22}{'null %':>10}{'sentinel %':>14}{'available %':>14}")
    for column in sorted(set(stats["nulls"]) | set(stats["sentinel_hits"])):
        null_rate = stats["nulls"].get(column, 0) / n_rows
        sentinel_rate = stats["sentinel_hits"].get(column, 0) / n_rows
        available = 1 - null_rate - sentinel_rate
        print(f"   {column:<22}{null_rate:>9.1%}{sentinel_rate:>14.1%}{available:>14.1%}")

    # --- Grain ---
    unique_keys = len(np.unique(stats["key_hashes"]))
    print(f"\nGrain check on {CANDIDATE_GRAIN}:")
    print(f"   rows        : {n_rows:,}")
    print(f"   unique keys : {unique_keys:,}")
    if unique_keys == n_rows:
        print("   -> candidate key is UNIQUE: usable as primary key")
    else:
        print(f"   -> NOT unique ({n_rows - unique_keys:,} collisions): grain is finer")

    # --- Source totals, to be reused as a dbt reconciliation test ---
    print("\nSource totals (reconciliation baseline):")
    for measure, value in stats["totals"].items():
        print(f"   {measure:<22}{value:>20,.2f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Full streaming scan of a raw source file.")
    parser.add_argument("--path", required=True, help="path to the raw CSV source")
    args = parser.parse_args()

    print("Scanning full source (this reads the whole file)...")
    report(scan(Path(args.path)))
    print("\nDone - paste this report into docs/adr/ADR-001-source-phmev.md")