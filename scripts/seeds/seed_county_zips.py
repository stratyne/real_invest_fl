"""
Seed the county_zips table for Escambia County by extracting
distinct ZIP codes from the raw NAL CSV.
Safe to run multiple times — uses INSERT ... ON CONFLICT DO NOTHING.

Usage:
    python -m scripts.seeds.seed_county_zips
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import pandas as pd
from sqlalchemy import create_engine, text
from config.settings import settings

COUNTY_FIPS   = "12033"   # Escambia
NAL_FILE_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', 'data', 'raw', 'NAL27F202502VAB.csv'
)
ZIP_COLUMN    = "PHY_ZIPCD"


def main() -> None:
    # ------------------------------------------------------------------ #
    # Extract distinct ZIP codes from NAL                                  #
    # ------------------------------------------------------------------ #
    print(f"Reading NAL file: {os.path.abspath(NAL_FILE_PATH)}")
    df = pd.read_csv(
        NAL_FILE_PATH,
        usecols=[ZIP_COLUMN],
        dtype={ZIP_COLUMN: str},
        low_memory=False,
    )

    zip_codes = (
        df[ZIP_COLUMN]
        .dropna()
        .str.strip()
        .str.zfill(5)          # ensure leading zeros are preserved
        .unique()
        .tolist()
    )
    zip_codes = [z for z in zip_codes if z.isdigit() and len(z) == 5]
    zip_codes.sort()

    print(f"Found {len(zip_codes)} distinct ZIP codes: {zip_codes}")

    # ------------------------------------------------------------------ #
    # Insert                                                               #
    # ------------------------------------------------------------------ #
    engine = create_engine(settings.sync_database_url, echo=False)

    insert_sql = text("""
        INSERT INTO county_zips (county_fips, zip_code, active)
        VALUES (:county_fips, :zip_code, true)
        ON CONFLICT (county_fips, zip_code) DO NOTHING
    """)

    rows = [
        {"county_fips": COUNTY_FIPS, "zip_code": z}
        for z in zip_codes
    ]

    with engine.begin() as conn:
        result = conn.execute(insert_sql, rows)
        print(f"Inserted {result.rowcount} ZIP codes for Escambia County.")


if __name__ == "__main__":
    main()
