"""
scripts/run_staging_import.py
------------------------------
Entry point for all staging file-drop parsers.

Runs all parsers in sequence, or a specific one via --source flag.

Usage:
    python scripts/run_staging_import.py                    # all sources
    python scripts/run_staging_import.py --source lis_pendens
    python scripts/run_staging_import.py --source foreclosure
    python scripts/run_staging_import.py --source tax_deed
    python scripts/run_staging_import.py --source zillow
    python scripts/run_staging_import.py --dry-run
    python scripts/run_staging_import.py --source lis_pendens --dry-run
    python scripts/run_staging_import.py --source zillow --dry-run
    python scripts/run_staging_import.py --source lis_pendens --file path/to/file.xlsx
    python scripts/run_staging_import.py --source zillow --file path/to/file.csv
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)

logger = logging.getLogger("run_staging_import")

# ---------------------------------------------------------------------------
# Source metadata — maps CLI source name to (source_key, display_name)
# source_key must match listing_events.source exactly
# ---------------------------------------------------------------------------
_SOURCE_META: dict[str, tuple[str, str]] = {
    "lis_pendens": ("escambia_landmarkweb",  "Lis Pendens (LandmarkWeb)"),
    "foreclosure": ("escambia_realforeclose", "Foreclosure (RealForeclose)"),
    "tax_deed":    ("escambia_realtaxdeed",   "Tax Deed (RealTaxDeed file-drop)"),
    "zillow":      ("zillow_foreclosure",     "Zillow (file-drop)"),
}

_COUNTY_FIPS = "12033"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run staging file-drop parsers for government data sources."
    )
    parser.add_argument(
        "--source",
        choices=["lis_pendens", "foreclosure", "tax_deed", "zillow", "all"],
        default="all",
        help="Which parser to run (default: all).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Parse and match but do not write to the database.",
    )
    parser.add_argument(
        "--file", type=Path, default=None,
        help="Process a single specific file (only valid with --source).",
    )
    args = parser.parse_args()

    if args.file and args.source == "all":
        parser.error("--file requires --source to be specified (not 'all')")

    sources = (
        [args.source] if args.source != "all"
        else ["lis_pendens", "foreclosure", "tax_deed", "zillow"]
    )

    for source in sources:
        print(f"\n{'='*60}")
        print(f"  Running parser: {source}")
        print(f"{'='*60}")

        source_key, display_name = _SOURCE_META[source]

        # ---------------------------------------------------------------- #
        # Step 1 — ingest execution                                         #
        # Each source runs independently. Failure of one does not stop      #
        # subsequent sources (preserves existing dispatcher behavior).      #
        # ---------------------------------------------------------------- #
        ingest_ok = True
        ingest_exc: Exception | None = None
        record_count: int | None = None

        try:
            if source == "lis_pendens":
                from real_invest_fl.ingest.staging_parsers.lis_pendens_parser import (
                    run_lis_pendens_import,
                )
                # run_lis_pendens_import() returns None — record_count stays None
                run_lis_pendens_import(dry_run=args.dry_run, specific_file=args.file)

            elif source == "foreclosure":
                from real_invest_fl.ingest.staging_parsers.foreclosure_parser import (
                    run_foreclosure_import,
                )
                totals = run_foreclosure_import(dry_run=args.dry_run, specific_file=args.file)
                if totals is not None:
                    record_count = totals.get("inserted")

            elif source == "tax_deed":
                from real_invest_fl.ingest.staging_parsers.tax_deed_parser import (
                    run_tax_deed_import,
                )
                totals = run_tax_deed_import(dry_run=args.dry_run, specific_file=args.file)
                if totals is not None:
                    record_count = totals.get("inserted")

            elif source == "zillow":
                from real_invest_fl.ingest.staging_parsers.zillow_parser import (
                    run_zillow_import,
                )
                totals = run_zillow_import(dry_run=args.dry_run, specific_file=args.file)
                if totals is not None:
                    record_count = totals.get("inserted")

        except Exception as exc:  # noqa: BLE001
            ingest_ok = False
            ingest_exc = exc
            logger.error(
                "Parser failed for source=%s: %s", source, exc, exc_info=True
            )

        # ---------------------------------------------------------------- #
        # Step 2 — status-table write (decoupled from ingest outcome)       #
        # Skipped entirely on dry-run — dry-run must never write status.    #
        # Failure here is logged as a status update failure only and does   #
        # not affect whether the loop continues to the next source.         #
        # ---------------------------------------------------------------- #
        if args.dry_run:
            continue

        try:
            from real_invest_fl.ingest.source_status import update_source_status
            from sqlalchemy import create_engine
            from config.settings import settings

            engine = create_engine(settings.sync_database_url)
            update_source_status(
                engine,
                source=source_key,
                display_name=display_name,
                county_fips=_COUNTY_FIPS,
                status="SUCCESS" if ingest_ok else "FAILED",
                record_count=record_count,
                error_message=None if ingest_ok else str(ingest_exc)[:500],
            )
        except Exception as status_exc:  # noqa: BLE001
            logger.warning(
                "Status table write failed for source=%s "
                "(ingest outcome unaffected): %s",
                source,
                status_exc,
            )


if __name__ == "__main__":
    main()
