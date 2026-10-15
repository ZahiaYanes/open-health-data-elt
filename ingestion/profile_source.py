"""
Raw source profiler.

Describes the real structure of a raw open-data file before any transformation
code is written. We never code against assumed column names, separators or code
values: the staging model and the column contract are written against facts.

What it reports:
- Detected encoding and delimiter (sniffed, not assumed)
- Column list and sample rows
- Null rate per column
- Full value domain of low-cardinality columns (coded dimensions)

Output is meant to be pasted into docs/adr/ADR-001-source-phmev.md

Author: Zahia Yanes
"""

import argparse
import csv
import zipfile
from pathlib import Path

import pandas as pd

# --- Configuration ---

TABULAR_SUFFIXES = (".csv", ".txt", ".tsv")
MAX_DISTINCT_TO_PRINT = 20   # above this, a column is not a coded dimension
SAMPLE_ROWS = 50_000         # enough to characterise the schema, fast to read
PEEK_BYTES = 200_000         # enough to sniff encoding and delimiter


def peek_bytes(path, n_bytes=PEEK_BYTES):
    """
    Read the first bytes of a source file, whether zipped or plain.

    Large CSVs are never fully loaded here: only a small head is read, so that
    encoding and delimiter can be detected cheaply.

    Parameters
    ----------
    path : pathlib.Path
        Path to a .csv/.txt file or a .zip archive containing one.
    n_bytes : int
        Number of bytes to read.

    Returns
    -------
    tuple of (str, bytes)
        Name of the tabular member and its first bytes.
    """
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            members = [
                name for name in archive.namelist()
                if name.lower().endswith(TABULAR_SUFFIXES)
            ]
            if not members:
                raise ValueError(f"No tabular file in archive: {archive.namelist()}")
            print(f"📦 Archive contents: {archive.namelist()}")
            with archive.open(members[0]) as handle:
                return members[0], handle.read(n_bytes)

    with open(path, "rb") as handle:
        return path.name, handle.read(n_bytes)


def sniff_format(sample):
    """
    Detect the encoding and the delimiter of a tabular sample.

    French public datasets are usually latin-1 encoded and semicolon separated,
    but this is verified rather than assumed.

    Parameters
    ----------
    sample : bytes
        First bytes of the file.

    Returns
    -------
    tuple of (str, str)
        Detected encoding and delimiter.
    """
    encoding = None
    for candidate in ("utf-8", "latin-1"):
        try:
            text = sample.decode(candidate)
            encoding = candidate
            break
        except UnicodeDecodeError:
            continue

    try:
        delimiter = csv.Sniffer().sniff(text[:5000], delimiters=";,\t|").delimiter
    except csv.Error:
        delimiter = ";"  # fallback: French public data default

    return encoding, delimiter


def read_sample(path, encoding, delimiter, nrows=SAMPLE_ROWS):
    """
    Read a bounded sample of the source, with every column as string.

    Typing is an explicit transformation step, never an inference side effect:
    reading everything as string prevents pandas from silently coercing codes
    (e.g. dropping the leading zero of a region code).

    Parameters
    ----------
    path : pathlib.Path
        Path to the source file or archive.
    encoding : str
        File encoding.
    delimiter : str
        Field separator.
    nrows : int
        Maximum number of rows to read.

    Returns
    -------
    pd.DataFrame
        Sample of the raw source, all columns as string.
    """
    options = {
        "sep": delimiter,
        "encoding": encoding,
        "dtype": str,
        "low_memory": False,
        "nrows": nrows,
    }

    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            member = next(
                name for name in archive.namelist()
                if name.lower().endswith(TABULAR_SUFFIXES)
            )
            with archive.open(member) as handle:
                return pd.read_csv(handle, **options)

    return pd.read_csv(path, **options)


def profile(path):
    """
    Print a full structural profile of a raw source file.

    Parameters
    ----------
    path : pathlib.Path
        Path to the source file or archive.

    Returns
    -------
    pd.DataFrame
        The sample that was profiled.
    """
    member, head = peek_bytes(path)
    encoding, delimiter = sniff_format(head)
    df = read_sample(path, encoding, delimiter)

    # --- Header ---
    print("\n" + "=" * 100)
    print(f"🔍 SOURCE PROFILE: {member}")
    print(f"   encoding={encoding!r} | delimiter={delimiter!r} | rows sampled={len(df):,}")
    print("=" * 100)

    # --- Schema ---
    print(f"\n📋 Columns ({len(df.columns)}):")
    print(f"   {list(df.columns)}\n")
    print(df.head(5).to_string())

    # --- Column-level profile ---
    print(f"\n📊 Column profile:")
    print(f"{'column':<28}{'nulls':>8}{'distinct':>10}  values / sample")
    print("-" * 110)
    for column in df.columns:
        series = df[column]
        distinct = series.nunique(dropna=True)
        # Low-cardinality columns are almost always coded dimensions
        # (sex, age band, region, flags): we need their full value domain.
        if distinct <= MAX_DISTINCT_TO_PRINT:
            preview = sorted(series.dropna().unique().tolist())
        else:
            preview = series.dropna().unique()[:3].tolist()
        print(f"{column:<28}{series.isna().mean():>7.1%}{distinct:>10}  {preview}")

    return df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Profile a raw open-data source file.")
    parser.add_argument("--path", required=True, help="path to the .csv or .zip source")
    args = parser.parse_args()

    print("🔄 Profiling raw source...")
    profile(Path(args.path))
    print("\n✅ Profiling done — paste this output into docs/adr/ADR-001-source-phmev.md")