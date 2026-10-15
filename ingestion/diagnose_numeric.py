"""
Numeric parsing diagnostic.

The dbt staging tests revealed ~500k NULL measures after ingestion, while the
raw source reports 0% NULL. The French-decimal conversion is therefore losing
data. This script inspects the raw strings that fail to parse, instead of
guessing the cause.

It also inspects negative values, which the range tests flagged, to tell a
parsing artefact from a genuine accounting adjustment.

Author: Zahia Yanes
"""

import argparse
import re
from collections import Counter
from pathlib import Path

import pandas as pd

# --- Configuration ---

ENCODING = "cp1252"
DELIMITER = ";"
CHUNK_SIZE = 500_000
MEASURES = ["boites", "rem", "bse"]
MAX_SAMPLES = 15

# Character patterns that could break a naive comma-to-dot conversion
PATTERNS = {
    "has_space": re.compile(r"\s"),
    "has_dot": re.compile(r"\."),
    "has_comma": re.compile(r","),
    "has_minus": re.compile(r"-"),
    "has_letter": re.compile(r"[A-Za-z]"),
    "is_empty": re.compile(r"^$"),
}


def naive_parse(series):
    """
    Reproduce the conversion currently used in the ingestion module.

    Parameters
    ----------
    series : pd.Series
        Raw string series.

    Returns
    -------
    pd.Series
        Float series, non-parsable values set to NaN.
    """
    return pd.to_numeric(series.str.replace(",", ".", regex=False), errors="coerce")


def diagnose(path):
    """
    Stream the raw source and characterise values that fail to parse.

    Parameters
    ----------
    path : pathlib.Path
        Path to the raw CSV file.

    Returns
    -------
    dict
        Diagnostic statistics per measure column.
    """
    stats = {
        measure: {
            "n_rows": 0,
            "n_unparsable": 0,
            "n_negative": 0,
            "samples_unparsable": [],
            "samples_negative": [],
            "patterns": Counter(),
            "max_length": 0,
        }
        for measure in MEASURES
    }

    reader = pd.read_csv(
        path, sep=DELIMITER, encoding=ENCODING, dtype=str,
        low_memory=False, chunksize=CHUNK_SIZE,
    )

    for i, chunk in enumerate(reader, start=1):
        chunk.columns = [c.strip().lower() for c in chunk.columns]

        for measure in MEASURES:
            raw = chunk[measure]
            parsed = naive_parse(raw)
            entry = stats[measure]
            entry["n_rows"] += len(raw)

            # Values present in the source but lost by the conversion
            lost = raw.notna() & parsed.isna()
            entry["n_unparsable"] += int(lost.sum())
            if lost.any():
                missing = MAX_SAMPLES - len(entry["samples_unparsable"])
                if missing > 0:
                    entry["samples_unparsable"].extend(
                        raw[lost].unique()[:missing].tolist()
                    )
                # Which characters do the failing values contain?
                failing = raw[lost].astype(str)
                for name, pattern in PATTERNS.items():
                    entry["patterns"][name] += int(failing.str.contains(pattern).sum())
                entry["max_length"] = max(entry["max_length"], int(failing.str.len().max()))

            # Negative values: parsing artefact or accounting adjustment?
            negative = parsed < 0
            entry["n_negative"] += int(negative.sum())
            if negative.any():
                missing = MAX_SAMPLES - len(entry["samples_negative"])
                if missing > 0:
                    entry["samples_negative"].extend(
                        raw[negative].unique()[:missing].tolist()
                    )

        print(f"   chunk {i:>3} processed", end="\r")

    print()
    return stats


def report(stats):
    """
    Print the diagnostic results.

    Parameters
    ----------
    stats : dict
        Output of diagnose().
    """
    print("\n" + "=" * 90)
    print("NUMERIC PARSING DIAGNOSTIC")
    print("=" * 90)

    for measure, entry in stats.items():
        n_rows = entry["n_rows"]
        print(f"\n--- {measure} ---")
        print(f"   rows            : {n_rows:,}")
        print(f"   unparsable      : {entry['n_unparsable']:,} "
              f"({entry['n_unparsable'] / n_rows:.2%})")
        print(f"   negative        : {entry['n_negative']:,}")
        print(f"   max raw length  : {entry['max_length']}")

        if entry["patterns"]:
            print("   characters found in unparsable values:")
            for name, count in entry["patterns"].most_common():
                print(f"      {name:<14} {count:>12,}")

        if entry["samples_unparsable"]:
            print(f"   unparsable samples : {entry['samples_unparsable']}")
        if entry["samples_negative"]:
            print(f"   negative samples   : {entry['samples_negative']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Diagnose numeric parsing failures.")
    parser.add_argument("--path", required=True, help="path to the raw CSV source")
    args = parser.parse_args()

    print("🔄 Diagnosing numeric parsing...")
    report(diagnose(Path(args.path)))
    print("\n✅ Done")