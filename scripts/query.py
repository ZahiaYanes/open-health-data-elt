"""
Ad-hoc query helper for the local DuckDB warehouse.

Avoids shell quoting issues and keeps exploratory queries reproducible.
The warehouse is opened read-only, so an exploratory query can never interfere
with a concurrent dbt build.

Usage
-----
    python -m scripts.query --list
    python -m scripts.query --table main_marts.dim_atc
    python -m scripts.query --sql "select count(*) from main_marts.dim_atc"
    python -m scripts.query --file scripts/sql/check_seed.sql

Author: Zahia Yanes
"""

import argparse
from pathlib import Path

import duckdb
import pandas as pd

WAREHOUSE = Path("warehouse/open_health.duckdb")

LIST_TABLES = """
SELECT table_schema, table_name, table_type
FROM information_schema.tables
WHERE table_schema <> 'information_schema'
ORDER BY table_schema, table_name
"""


def run(sql):
    """
    Execute a query against the local warehouse.

    Parameters
    ----------
    sql : str
        SQL statement to execute.

    Returns
    -------
    pd.DataFrame
        Query result.
    """
    if not WAREHOUSE.exists():
        raise FileNotFoundError(f"{WAREHOUSE} not found - run `make build` first.")

    # read_only avoids locking the file against a running dbt process.
    with duckdb.connect(str(WAREHOUSE), read_only=True) as connection:
        return connection.sql(sql).df()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Query the local DuckDB warehouse.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--sql", help="raw SQL statement")
    group.add_argument("--file", help="path to a .sql file")
    group.add_argument("--table", help="fully qualified table name to preview")
    group.add_argument("--list", action="store_true", help="list all tables and views")
    parser.add_argument("--limit", type=int, default=50, help="row limit for --table")
    args = parser.parse_args()

    if args.list:
        query = LIST_TABLES
    elif args.table:
        query = f"SELECT * FROM {args.table} LIMIT {args.limit}"
    elif args.file:
        query = Path(args.file).read_text()
    else:
        query = args.sql

    pd.set_option("display.max_columns", None, "display.width", 250)
    print(run(query).to_string(index=False))