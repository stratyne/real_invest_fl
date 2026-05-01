#!/usr/bin/env python3
"""
Runner for the Escambia County Clerk Tax Deed Sale scraper.

Usage:
    python real_invest_fl/ingest/run_taxdeed.py --upcoming
    python real_invest_fl/ingest/run_taxdeed.py --historical
    python real_invest_fl/ingest/run_taxdeed.py --date 5/6/2026
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# ROOT path bootstrap
# File:  real_invest_fl/ingest/run_taxdeed.py
#   .parent  →  real_invest_fl/ingest/
#   .parent  →  real_invest_fl/
#   .parent  →  project root
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine                                  # noqa: E402
from config.settings import settings                                  # noqa: E402
from real_invest_fl.scrapers.escambia_taxdeed_clerk import run        # noqa: E402
from real_invest_fl.ingest.source_status import update_source_status  # noqa: E402

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

logger = logging.getLogger("run_taxdeed_scraper")

# ---------------------------------------------------------------------------
# Source identity — matches listing_events.source exactly
# ---------------------------------------------------------------------------
_SOURCE       = "escambia_clerk_taxsale"
_DISPLAY_NAME = "Escambia Clerk \u2013 Tax Deed"
_COUNTY_FIPS  = "12033"


def _parse_date_arg(value: str):
    """Parse M/D/YYYY CLI argument to a date object.

    Uses manual integer splitting — avoids the non-portable %-m/%-d/%Y
    strptime flag while correctly handling non-zero-padded input such
    as '5/6/2026'.  Raises argparse.ArgumentTypeError on bad input so
    argparse prints a clean usage message rather than a stack trace.
    """
    parts = value.strip().split("/")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError(
            f"Invalid date {value!r}. Expected format: M/D/YYYY (e.g. 5/6/2026)"
        )
    try:
        month, day, year = int(parts[0]), int(parts[1]), int(parts[2])
        return datetime(year, month, day).date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid date {value!r}: {exc}"
        ) from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Scrape Escambia County Clerk tax deed sale records "
            "and insert into listing_events."
        )
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--historical",
        action="store_true",
        help="Scrape all sale dates from 2019-01-01 through today.",
    )
    group.add_argument(
        "--upcoming",
        action="store_true",
        help="Scrape only future (today or later) sale dates.",
    )
    group.add_argument(
        "--date",
        metavar="M/D/YYYY",
        type=_parse_date_arg,
        help="Scrape a single specific sale date, e.g. 5/6/2026.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    engine = create_engine(settings.sync_database_url)

    # ------------------------------------------------------------------ #
    # Step 1 — ingest execution                                           #
    # Outcome captured independently before any status-table write.       #
    # ------------------------------------------------------------------ #
    ingest_ok = True
    ingest_exc: Exception | None = None

    try:
        if args.historical:
            run(mode="historical", engine=engine)
        elif args.upcoming:
            run(mode="upcoming", engine=engine)
        else:
            run(mode="single", single_date=args.date, engine=engine)
    except Exception as exc:  # noqa: BLE001
        ingest_ok = False
        ingest_exc = exc
        logger.error("Tax deed scraper failed: %s", exc, exc_info=True)

    # ------------------------------------------------------------------ #
    # Step 2 — status-table write (decoupled from ingest outcome)         #
    # Failure here is logged as a status update failure only.             #
    # run() does not return a record count — record_count left as None.   #
    # ------------------------------------------------------------------ #
    try:
        update_source_status(
            engine,
            source=_SOURCE,
            display_name=_DISPLAY_NAME,
            county_fips=_COUNTY_FIPS,
            status="SUCCESS" if ingest_ok else "FAILED",
            error_message=None if ingest_ok else str(ingest_exc)[:500],
        )
    except Exception as status_exc:  # noqa: BLE001
        logger.warning(
            "Status table write failed (ingest outcome unaffected): %s",
            status_exc,
        )

    return 0 if ingest_ok else 1


if __name__ == "__main__":
    sys.exit(main())
