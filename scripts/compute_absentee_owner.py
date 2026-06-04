#!/usr/bin/env python3
"""
compute_absentee_owner.py

Recomputes absentee_owner for all SFR parcels in the DB using the
corrected logic: OWN_ADDR2 is the mailing street address field.
OWN_ADDR1 is the owner name field and is ignored for address comparison.

Logic (per _compute_absentee in nal_ingest.py):
    1. Out-of-state owner (own_state not FL) -- True (absentee).
    2. OWN_ADDR2 starts with a digit -- compare against PHY_ADDR1.
       Match = False (owner-occupied). Mismatch = True (absentee).
    3. No usable mailing street -- None (undeterminable, stored as NULL).

Usage:
    python scripts/compute_absentee_owner.py --county-fips 12113
    python scripts/compute_absentee_owner.py --county-fips 12113 --dry-run
    python scripts/compute_absentee_owner.py --county-fips 12033
"""

import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import settings

BATCH_SIZE = 5000


# County-specific mailing address field. Verified against raw NAL data.
_MAILING_ADDR_FIELD: dict[str, str] = {
    "12033": "own_addr1",  # Escambia
    "12113": "own_addr2",  # Santa Rosa
}


def compute(
    own_state: str | None,
    mailing_addr: str | None,
    phy_addr1: str | None,
) -> bool | None:
    own_state    = (own_state    or "").strip().upper()
    mailing_addr = (mailing_addr or "").strip().upper()
    phy_addr1    = (phy_addr1    or "").strip().upper()

    if own_state and own_state != "FL":
        return True

    if not mailing_addr:
        return None

    if mailing_addr.startswith("PO ") or mailing_addr.startswith("P.O."):
        return True

    if not mailing_addr[0].isdigit():
        return None

    if not phy_addr1:
        return None

    return mailing_addr != phy_addr1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recompute absentee_owner for SFR parcels."
    )
    parser.add_argument("--county-fips", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    engine = create_engine(settings.host_sync_database_url)
    mailing_field_db = _MAILING_ADDR_FIELD.get(args.county_fips, "own_addr2")

    with engine.connect() as conn:
        rows = conn.execute(
            text(f"""
                SELECT parcel_id, own_state, {mailing_field_db} AS mailing_addr, phy_addr1
                FROM properties
                WHERE county_fips = :fips
                  AND dor_uc = '001'
                ORDER BY parcel_id
            """),
            {"fips": args.county_fips},
        ).fetchall()

    print(f"[fetch] {len(rows):,} SFR parcels loaded for county {args.county_fips}.")
    print(f"[config] mailing address field: {mailing_field_db}")

    absentee  = []
    occupied  = []
    null_rows = []

    for row in rows:
        result = compute(row.own_state, row.mailing_addr, row.phy_addr1)
        if result is True:
            absentee.append(row.parcel_id)
        elif result is False:
            occupied.append(row.parcel_id)
        else:
            null_rows.append(row.parcel_id)

    print(f"[compute] absentee:       {len(absentee):,}")
    print(f"[compute] owner-occupied: {len(occupied):,}")
    print(f"[compute] undeterminable: {len(null_rows):,}")

    if args.dry_run:
        print("[done] Dry run complete. No changes written.")
        return

    def update_batches(conn, parcel_ids: list, value) -> int:
        updated = 0
        for i in range(0, len(parcel_ids), BATCH_SIZE):
            batch = parcel_ids[i:i + BATCH_SIZE]
            conn.execute(
                text("""
                    UPDATE properties
                    SET absentee_owner = :val
                    WHERE county_fips = :fips
                      AND parcel_id = ANY(:ids)
                """),
                {"val": value, "fips": args.county_fips, "ids": batch},
            )
            updated += len(batch)
        return updated

    with engine.begin() as conn:
        u1 = update_batches(conn, absentee,  True)
        u2 = update_batches(conn, occupied,  False)
        u3 = update_batches(conn, null_rows, None)

    print(f"[write] absentee set True:  {u1:,}")
    print(f"[write] occupied set False: {u2:,}")
    print(f"[write] NULL set:           {u3:,}")
    print("[done] absentee_owner recomputed.")


if __name__ == "__main__":
    main()
