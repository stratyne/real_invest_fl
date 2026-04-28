#!/usr/bin/env python3
"""
real_invest_fl/ingest/run_auction_com.py
-----------------------------------------
Runner for the Auction.com Escambia County scraper.

Fetches active listings from the Auction.com GraphQL API and
inserts matched records into listing_events.

Usage:
    python real_invest_fl/ingest/run_auction_com.py
    python real_invest_fl/ingest/run_auction_com.py --dry-run
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# ── path bootstrap ─────────────────────────────────────────────────────────
# File: real_invest_fl/ingest/run_auction_com.py
#   .parent -> real_invest_fl/ingest/
#   .parent -> real_invest_fl/
#   .parent -> project root
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine          # noqa: E402
from config.settings import settings          # noqa: E402
from real_invest_fl.scrapers.auction_com import run  # noqa: E402

# ── logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

logger = logging.getLogger("run_auction_com")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch Auction.com Escambia County FL listings "
            "and insert into listing_events."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Fetch and match but do not write to the database. "
            "Prints [REVIEW] items and match summary."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.dry_run:
        logger.info("DRY-RUN mode — no database writes will occur")
        # Dry-run: fetch and match only, log what would be inserted
        # Import internal helpers directly for inspection
        from real_invest_fl.scrapers.auction_com import (
            _fetch_listings,
            _is_escambia_fl,
            _build_address,
            _signal_type,
            _safe_int,
            _safe_float,
            _parse_auction_date,
            _listing_url,
            _lookup_parcel,
            _get_filter_profile_id,
            _get_existing_listing_ids,
            COUNTY_FIPS,
            SOURCE_NAME,
        )

        engine = create_engine(settings.sync_database_url, echo=False)
        all_listings = _fetch_listings()
        fl_listings  = [l for l in all_listings if _is_escambia_fl(l)]

        logger.info(
            "Fetched %d total, %d Escambia FL",
            len(all_listings), len(fl_listings),
        )

        matched = skipped = unmatched = 0

        with engine.connect() as conn:
            existing_ids = _get_existing_listing_ids(conn)

            for listing in fl_listings:
                listing_id = str(listing.get("listing_id", "")).strip()

                if listing_id in existing_ids:
                    skipped += 1
                    continue

                full_address, street_norm, zip_code = _build_address(listing)
                if not street_norm:
                    print(f"[REVIEW] listing_id={listing_id} has no street address")
                    unmatched += 1
                    continue

                parcel = _lookup_parcel(conn, street_norm, zip_code)

                if parcel is None:
                    print(
                        f"[REVIEW] No parcel match for listing_id={listing_id} "
                        f"address={full_address!r}"
                    )
                    unmatched += 1
                    continue

                matched += 1
                summary = (
                    (listing.get("primary_property") or {})
                    .get("summary") or {}
                )
                logger.info(
                    "[DRY-RUN] Would insert | listing_id=%s | address=%s | "
                    "price=$%s | signal_type=%s | parcel=%s | "
                    "beds=%s baths=%s",
                    listing_id,
                    full_address,
                    listing.get("auction", {}).get("starting_bid"),
                    _signal_type(listing),
                    parcel["parcel_id"],
                    _safe_int(summary.get("total_bedrooms")),
                    _safe_float(summary.get("total_bathrooms")),
                )

        logger.info(
            "DRY-RUN complete | escambia_fl=%d matched=%d "
            "skipped=%d unmatched=%d",
            len(fl_listings), matched, skipped, unmatched,
        )
        return 0

    # Live run
    engine = create_engine(settings.sync_database_url, echo=False)
    run(engine=engine)
    return 0


if __name__ == "__main__":
    sys.exit(main())
