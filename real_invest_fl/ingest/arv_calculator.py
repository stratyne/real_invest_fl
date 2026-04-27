"""
real_invest_fl/ingest/arv_calculator.py
----------------------------------------
ARV Calculation Pipeline — Phase 1, Action 3.

Computes and writes ARV-related metrics to the properties table for all
MQI-qualified parcels. Uses Just Value (jv) as the ARV proxy per the
locked strategic decision — this field can be replaced by the SDF comp
engine in a future phase without touching jv.

Columns written per parcel:
    jv_per_sqft   — NUMERIC  : jv / tot_lvg_area (NULL if tot_lvg_area is NULL)
    arv_estimate  — INTEGER  : mirrors jv (ARV proxy, overridable later)
    arv_spread    — INTEGER  : arv_estimate - list_price (NULL until Phase 2
                               scrapers populate list_price)

NOTE: list_price is NOT written here. It will be populated by Phase 2
scraper/matcher modules. arv_spread will remain NULL for all parcels
until list_price is available.

Only MQI-qualified parcels are processed. Already-calculated parcels are
skipped unless --force is passed.

Usage:
    python -m real_invest_fl.ingest.arv_calculator [options]

Options:
    --dry-run       Compute metrics but do not write to database.
    --force         Recalculate all qualified parcels, even if already done.
    --batch-size N  Rows per transaction batch (default: 500).

ETHICAL / LEGAL NOTICE:
    All data is sourced from the Florida DOR NAL — a public government
    dataset. No scraping or rate limiting is required for this module.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, text

# ── path bootstrap ────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import settings  # noqa: E402

# ── logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("arv_calculator")

# ── constants ─────────────────────────────────────────────────────────────────
DEFAULT_BATCH = 500


# ── helpers ───────────────────────────────────────────────────────────────────

def _chunks(lst: list, size: int) -> Iterator[list]:
    """Yield successive chunks of `size` from `lst`."""
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


def _compute_metrics(row: dict) -> dict:
    """
    Compute ARV metrics for a single parcel row.

    Args:
        row: dict with keys parcel_id, jv, tot_lvg_area, list_price.

    Returns:
        dict with keys parcel_id, jv_per_sqft, arv_estimate, arv_spread.
    """
    parcel_id    = row["parcel_id"]
    jv           = row["jv"]           # always present — verified by pre-query
    tot_lvg_area = row["tot_lvg_area"] # may be None
    list_price   = row["list_price"]   # None for all parcels at Phase 1

    # arv_estimate — just value is the ARV proxy
    arv_estimate: int = jv

    # jv_per_sqft — only computable when tot_lvg_area is present and non-zero
    jv_per_sqft: Decimal | None = None
    if tot_lvg_area and tot_lvg_area > 0:
        jv_per_sqft = round(Decimal(jv) / Decimal(tot_lvg_area), 2)

    # arv_spread — only computable when list_price is present and non-zero
    arv_spread: int | None = None
    if list_price and list_price > 0:
        arv_spread = arv_estimate - list_price

    return {
        "parcel_id":    parcel_id,
        "jv_per_sqft":  jv_per_sqft,
        "arv_estimate": arv_estimate,
        "arv_spread":   arv_spread,
    }


# ── core pipeline ─────────────────────────────────────────────────────────────

def run_arv_calculation(dry_run: bool, force: bool, batch_size: int) -> None:
    """
    Full ARV calculation pipeline.

    Steps:
        1. Connect to database.
        2. Load all MQI-qualified parcels requiring calculation.
        3. Compute metrics for each parcel.
        4. Batch-update jv_per_sqft, arv_estimate, arv_spread.
        5. Log summary.
    """
    t_start = time.time()

    logger.info("Connecting to database...")
    engine = create_engine(settings.sync_database_url, echo=False)

    # ── Step 2 — Load parcels ─────────────────────────────────────────────── #
    # In force mode: load all MQI-qualified parcels.
    # In normal mode: load only parcels where arv_estimate IS NULL
    # (i.e., not yet calculated). This makes the script safely resumable.
    if force:
        where_clause = "WHERE mqi_qualified = true"
        logger.info("--force mode: loading ALL MQI-qualified parcels...")
    else:
        where_clause = "WHERE mqi_qualified = true AND arv_estimate IS NULL"
        logger.info("Normal mode: loading parcels with arv_estimate IS NULL...")

    fetch_sql = text(f"""
        SELECT
            parcel_id,
            jv,
            tot_lvg_area,
            list_price
        FROM properties
        {where_clause}
        ORDER BY parcel_id
    """)

    with engine.connect() as conn:
        result = conn.execute(fetch_sql)
        rows = [dict(r._mapping) for r in result.fetchall()]

    total = len(rows)
    logger.info("Loaded %d parcels for ARV calculation", total)

    if total == 0:
        logger.info("No parcels require ARV calculation — all up to date.")
        return

    # ── Step 3 — Compute metrics ──────────────────────────────────────────── #
    logger.info("Computing ARV metrics...")

    computed = [_compute_metrics(row) for row in rows]

    # Diagnostic counts
    has_jv_per_sqft = sum(1 for r in computed if r["jv_per_sqft"] is not None)
    has_arv_spread  = sum(1 for r in computed if r["arv_spread"]  is not None)
    no_sqft         = total - has_jv_per_sqft

    logger.info(
        "Metrics computed | arv_estimate=%d | jv_per_sqft=%d | "
        "arv_spread=%d | no_sqft_skipped=%d",
        total, has_jv_per_sqft, has_arv_spread, no_sqft,
    )

    if no_sqft > 0:
        logger.info(
            "%d parcels have NULL tot_lvg_area — jv_per_sqft will be NULL for these.",
            no_sqft,
        )
    if has_arv_spread == 0:
        logger.info(
            "arv_spread is NULL for all parcels — expected at Phase 1 "
            "(list_price not yet populated)."
        )

    if dry_run:
        logger.info("[DRY-RUN] Sample of first 5 computed rows:")
        for row in computed[:5]:
            logger.info(
                "  parcel_id=%-20s arv_estimate=%-8s "
                "jv_per_sqft=%-8s arv_spread=%s",
                row["parcel_id"],
                row["arv_estimate"],
                row["jv_per_sqft"],
                row["arv_spread"],
            )
        logger.info("[DRY-RUN] No data written to database.")
        return

    # ── Step 4 — Batch update ─────────────────────────────────────────────── #
    total_batches = (len(computed) + batch_size - 1) // batch_size
    total_updated = 0

    logger.info(
        "Writing to database in %d batches of up to %d rows...",
        total_batches, batch_size,
    )

    update_sql = text("""
        UPDATE properties
        SET
            jv_per_sqft   = :jv_per_sqft,
            arv_estimate  = :arv_estimate,
            arv_spread    = :arv_spread,
            updated_at    = NOW()
        WHERE parcel_id = :parcel_id
    """)

    for batch_num, batch in enumerate(_chunks(computed, batch_size), start=1):
        # Independent transaction per batch — same pattern as gis_ingest.py.
        # Prevents long-held locks from blocking the concurrent CAMA scraper.
        with engine.begin() as conn:
            conn.execute(update_sql, batch)
        total_updated += len(batch)

        if batch_num % 10 == 0 or batch_num == total_batches:
            elapsed = time.time() - t_start
            pct = total_updated / len(computed) * 100
            logger.info(
                "Batch %d/%d — %d rows written (%.1f%%) — %.1fs elapsed",
                batch_num, total_batches, total_updated, pct, elapsed,
            )

    # ── Step 5 — Summary ─────────────────────────────────────────────────── #
    elapsed = time.time() - t_start
    logger.info(
        "ARV calculation complete | processed=%d updated=%d "
        "no_sqft=%d duration=%.1fs",
        total, total_updated, no_sqft, elapsed,
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute and store ARV metrics for all MQI-qualified parcels."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Compute metrics but do not write to the database.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Recalculate all qualified parcels, even if arv_estimate is already set.",
    )
    parser.add_argument(
        "--batch-size", type=int, default=DEFAULT_BATCH,
        help=f"Rows per transaction batch (default: {DEFAULT_BATCH}).",
    )
    args = parser.parse_args()

    run_arv_calculation(
        dry_run=args.dry_run,
        force=args.force,
        batch_size=args.batch_size,
    )


if __name__ == "__main__":
    main()
