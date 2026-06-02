"""
scripts/compute_years_since_last_sale.py
-----------------------------------------
Backfill years_since_last_sale on the properties table using
parcel_sale_history as the primary source.

For parcels with parcel_sale_history rows, computes:
    EXTRACT(YEAR FROM AGE(NOW(), MAX(sale_date)))::INTEGER

For parcels with no parcel_sale_history rows, the existing
NAL-derived value (asmnt_yr - sale_yr1) is left unchanged.

Safe to re-run — idempotent. Always uses current date so values
stay accurate on each run.

Usage:
    python scripts/compute_years_since_last_sale.py
    python scripts/compute_years_since_last_sale.py --county 12113
    python scripts/compute_years_since_last_sale.py --dry-run
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import settings  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("compute_years_since_last_sale")


def run(county: str | None, dry_run: bool) -> None:
    engine = create_engine(settings.host_sync_database_url, echo=False)

    county_clause = "AND p.county_fips = :county" if county else ""
    params: dict = {}
    if county:
        params["county"] = county

    # ── Step 1: count affected rows ───────────────────────────────────
    count_sql = text(f"""
        SELECT COUNT(*)
        FROM properties p
        WHERE EXISTS (
            SELECT 1
            FROM parcel_sale_history psh
            WHERE psh.county_fips = p.county_fips
              AND psh.parcel_id   = p.parcel_id
              AND psh.sale_date   IS NOT NULL
        )
        {county_clause}
    """)

    with engine.connect() as conn:
        affected = conn.execute(count_sql, params).scalar()

    logger.info(
        "Parcels with parcel_sale_history to update: %d%s",
        affected,
        f" (county {county})" if county else " (all counties)",
    )

    if dry_run:
        logger.info("[DRY-RUN] No writes performed.")
        return

    # ── Step 2: update ────────────────────────────────────────────────
    update_sql = text(f"""
        UPDATE properties p
        SET
            years_since_last_sale = EXTRACT(
                YEAR FROM AGE(NOW(), psh.max_sale_date)
            )::INTEGER,
            updated_at = NOW()
        FROM (
            SELECT
                county_fips,
                parcel_id,
                MAX(sale_date) AS max_sale_date
            FROM parcel_sale_history
            WHERE sale_date IS NOT NULL
            GROUP BY county_fips, parcel_id
        ) psh
        WHERE p.county_fips = psh.county_fips
          AND p.parcel_id   = psh.parcel_id
          {county_clause}
    """)

    with engine.begin() as conn:
        result = conn.execute(update_sql, params)
        logger.info("Rows updated: %d", result.rowcount)

    logger.info("years_since_last_sale backfill complete.")
    engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill years_since_last_sale from parcel_sale_history."
    )
    parser.add_argument(
        "--county",
        type=str,
        default=None,
        help="Restrict update to a single county_fips value (e.g. 12113).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count affected rows but do not write to the database.",
    )
    args = parser.parse_args()
    run(county=args.county, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
