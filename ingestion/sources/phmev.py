"""
Open PHMEV ingestion.

Loads the raw Open PHMEV file (hospital-prescribed drugs dispensed in community
pharmacies, published by the French National Health Insurance) into the landing
zone as partitioned Parquet.

Design principle
----------------
The landing zone is a faithful, typed copy of the source. This module performs
*structural* work only:

- reads the file in chunks (3.5M rows, constant memory)
- decodes cp1252, strips corrupted control characters from labels
- lowercases and renames columns to a stable English contract
- converts French decimal numbers to float
- drops out-of-scope columns (postal street address)
- adds partition and lineage metadata

Publisher sentinels (9999999, 99, 9...) are **deliberately preserved**: turning
them into NULL is a semantic decision, handled and tested in the dbt staging
layer. See docs/adr/ADR-001-source-phmev.md

Author: Zahia Yanes
"""

import argparse
import logging
import re
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

log = logging.getLogger(__name__)

# --- Configuration ---

LANDING_DIR = Path("data/landing/phmev")
ENCODING = "cp1252"   # confirmed in ADR-001: latin-1 corrupts right quotes
DELIMITER = ";"
CHUNK_SIZE = 500_000

# Source column (lowercased) -> stable English contract
COLUMN_MAP = {
    # therapeutic classification (WHO ATC, 5 levels)
    "atc1": "atc_level_1", "l_atc1": "atc_level_1_label",
    "atc2": "atc_level_2", "l_atc2": "atc_level_2_label",
    "atc3": "atc_level_3", "l_atc3": "atc_level_3_label",
    "atc4": "atc_level_4", "l_atc4": "atc_level_4_label",
    "atc5": "atc_level_5", "l_atc5": "atc_level_5_label",
    # product
    "cip13": "cip13", "l_cip13": "product_label",
    "top_gen": "generic_status_code", "gen_num": "generic_group_id",
    # patient profile
    "age": "age_band_code", "sexe": "sex_code",
    # prescribing facility
    "etb_rgt": "facility_id",
    "nom_etb": "facility_name",
    "raison_sociale_etb": "facility_legal_name",
    "categorie_jur": "facility_category_code",
    "categorie_jur_rgt": "facility_category_group",
    "code_postal": "postal_code",
    "nom_ville": "city_name",
    "region_etb": "facility_region_code",
    # disclosure-control flags
    "top_etb_age": "facility_reports_age",
    "top_etb_sexe": "facility_reports_sex",
    # measures
    "boites": "n_boxes", "rem": "amount_reimbursed_eur", "bse": "amount_base_eur",
}

# Dropped: postal street address, no analytical value (ADR-001)
DROPPED_COLUMNS = ["nom_voie", "numero_voie"]

# Columns that must exist, otherwise the source contract is broken
REQUIRED_COLUMNS = {"atc1", "atc5", "cip13", "age", "sexe", "etb_rgt",
                    "boites", "rem", "bse"}

NUMERIC_COLUMNS = ["n_boxes", "amount_reimbursed_eur", "amount_base_eur"]
TEXT_COLUMNS = [c for c in COLUMN_MAP.values() if c.endswith(("_label", "_name"))]

# C0/C1 control characters left by the publisher's export (e.g. \x1a instead of "é")
CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def validate_contract(columns, source_name):
    """
    Check that the source still exposes the columns the pipeline relies on.

    Parameters
    ----------
    columns : set of str
        Lowercased column names found in the file.
    source_name : str
        Source identifier, used in the error message.

    Raises
    ------
    ValueError
        If any required column is missing.
    """
    missing = REQUIRED_COLUMNS - columns
    if missing:
        raise ValueError(f"[{source_name}] broken source contract, missing: {sorted(missing)}")


def clean_text(series):
    """
    Remove corrupted control characters and normalise whitespace in a label.

    The publisher's export contains control characters where accented letters
    are expected (e.g. "Non restitu\\x1a"). They are stripped rather than
    guessed: the corresponding rows are identified by their sentinel code.

    Parameters
    ----------
    series : pd.Series
        Raw string series.

    Returns
    -------
    pd.Series
        Cleaned string series.
    """
    return (
        series.str.replace(CONTROL_CHARS, "", regex=True)
        .str.strip()
        .str.replace(r"\s+", " ", regex=True)
        .replace("", None)
    )


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

def transform_chunk(chunk, year, source_file):
    """
    Apply structural transformations to one chunk of the raw source.

    Parameters
    ----------
    chunk : pd.DataFrame
        Raw chunk, all columns as string.
    year : int
        Reference year, taken from the filename (the source has no date column).
    source_file : str
        Original filename, kept for lineage.

    Returns
    -------
    pd.DataFrame
        Chunk conforming to the landing contract.
    """
    chunk.columns = [c.strip().lower() for c in chunk.columns]
    chunk = chunk.drop(columns=[c for c in DROPPED_COLUMNS if c in chunk.columns])
    chunk = chunk.rename(columns=COLUMN_MAP)

    for column in TEXT_COLUMNS:
        if column in chunk.columns:
            chunk[column] = clean_text(chunk[column])

    for column in NUMERIC_COLUMNS:
        chunk[column] = to_numeric_fr(chunk[column])

    # The source has no time column: the period only exists in the filename.
    chunk["reference_year"] = year
    chunk["_source_file"] = source_file
    chunk["_ingested_at"] = pd.Timestamp.utcnow()

    return chunk


def run(path, year, landing_dir=LANDING_DIR):
    """
    Ingest the raw Open PHMEV file into the landing zone.

    The file is streamed chunk by chunk and appended to a single Parquet file,
    so that memory stays flat regardless of the source size.

    Parameters
    ----------
    path : pathlib.Path
        Path to the raw CSV file.
    year : int
        Reference year used for partitioning.
    landing_dir : pathlib.Path
        Root of the landing zone.

    Returns
    -------
    pathlib.Path
        Path of the written Parquet file.
    """
    output_dir = landing_dir / f"year={year}"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "data.parquet"

    reader = pd.read_csv(
        path, sep=DELIMITER, encoding=ENCODING, dtype=str,
        low_memory=False, chunksize=CHUNK_SIZE,
    )

    writer = None
    n_rows = 0
    try:
        for i, chunk in enumerate(reader, start=1):
            if i == 1:
                validate_contract({c.strip().lower() for c in chunk.columns}, path.name)

            frame = transform_chunk(chunk, year, path.name)
            table = pa.Table.from_pandas(frame, preserve_index=False)

            # The schema of the first chunk becomes the contract for the whole file.
            if writer is None:
                writer = pq.ParquetWriter(output_path, table.schema, compression="snappy")
            writer.write_table(table)

            n_rows += len(frame)
            log.info("chunk %s | %s rows written", i, f"{n_rows:,}")
    finally:
        if writer is not None:
            writer.close()

    size_mb = output_path.stat().st_size / 1e6
    log.info("✅ %s rows -> %s (%.1f MB)", f"{n_rows:,}", output_path, size_mb)
    return output_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    parser = argparse.ArgumentParser(description="Ingest Open PHMEV into the landing zone.")
    parser.add_argument("--path", required=True, help="path to the raw CSV file")
    parser.add_argument("--year", required=True, type=int, help="reference year, e.g. 2025")
    args = parser.parse_args()

    print("🔄 Ingesting Open PHMEV...")
    run(Path(args.path), args.year)