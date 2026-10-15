"""
Isolate a seed CSV loading failure.

dbt-duckdb loads seeds through DuckDB's native CSV reader rather than through
Python. When the sniffer fails, the error surfaces as a dbt error, which hides
whether the problem comes from the file, from DuckDB, or from the options dbt
passes. This script reads the file with several explicit option sets to tell
them apart.

Usage
-----
    python -m scripts.debug_seed_csv --path transform/seeds/seed_critical_antibiotics.csv

Author: Zahia Yanes
"""

import argparse
from pathlib import Path

import duckdb

# Progressively more explicit option sets: the first one that works tells us
# which assumption DuckDB was unable to infer on its own.
ATTEMPTS = {
    "auto (no options)": "SELECT * FROM read_csv('{path}')",
    "header only": "SELECT * FROM read_csv('{path}', header = true)",
    "delim + header": "SELECT * FROM read_csv('{path}', delim = ',', header = true)",
    "delim + quote + header": (
        "SELECT * FROM read_csv('{path}', delim = ',', quote = '\"', header = true)"
    ),
    "all_varchar": (
        "SELECT * FROM read_csv('{path}', delim = ',', header = true, all_varchar = true)"
    ),
    "csv_auto": "SELECT * FROM read_csv_auto('{path}')",
}


def debug(path):
    """
    Try to read a CSV file with increasingly explicit options.

    Parameters
    ----------
    path : pathlib.Path
        Path to the CSV file.
    """
    print(f"duckdb version : {duckdb.__version__}")
    print(f"file           : {path}")
    print(f"size           : {path.stat().st_size} bytes")

    raw = path.read_bytes()
    print(f"starts with BOM: {raw.startswith(b'\xef\xbb\xbf')}")
    print(f"contains CR    : {b'\\r' in raw}")
    print(f"ends with LF   : {raw.endswith(b'\\n')}")
    print()

    for label, template in ATTEMPTS.items():
        try:
            frame = duckdb.sql(template.format(path=path)).df()
            print(f"  OK   {label:<24} -> {frame.shape[0]} rows x {frame.shape[1]} cols")
        except Exception as error:  # noqa: BLE001 - we want to report any failure
            first_line = str(error).splitlines()[0]
            print(f"  FAIL {label:<24} -> {first_line}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Debug a seed CSV loading failure.")
    parser.add_argument("--path", required=True, help="path to the CSV file")
    debug(Path(parser.parse_args().path))