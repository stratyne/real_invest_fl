"""
scripts/run_escambia_cama.py
------------------------------
Unattended wrapper for the Escambia CAMA scraper.

ECPA enforces a rolling request limit. The scraper stops cleanly on
soft-block detection. This wrapper restarts it automatically after a
configurable wait period.

Each restart picks up where the previous run left off via
cama_enriched_at IS NULL — no duplicate work, no force flag needed.

Usage:
    python scripts/run_escambia_cama.py
    python scripts/run_escambia_cama.py --wait 480
    python scripts/run_escambia_cama.py --dry-run
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, text  # noqa: E402
from config.settings import settings        # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("run_escambia_cama")

DEFAULT_WAIT = 420


def remaining_parcel_count() -> int:
    engine = create_engine(settings.host_sync_database_url)
    with engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT COUNT(*) FROM properties "
                "WHERE county_fips = '12033' "
                "AND dor_uc = '001' "
                "AND cama_enriched_at IS NULL"
            )
        )
        count = result.scalar()
    engine.dispose()
    return int(count)


def run(wait: int, dry_run: bool) -> None:
    cmd = [
        sys.executable,
        "-m", "real_invest_fl.ingest.cama.escambia",
    ]
    if dry_run:
        cmd.append("--dry-run")

    run_number = 0

    while True:
        run_number += 1
        logger.info("Starting Escambia CAMA run #%d", run_number)

        result = subprocess.run(cmd, cwd=ROOT)

        if result.returncode != 0:
            logger.error(
                "Run #%d exited with code %d — stopping wrapper.",
                run_number, result.returncode,
            )
            break

        remaining = remaining_parcel_count()

        if remaining == 0:
            logger.info("All Escambia parcels enriched. Wrapper complete.")
            break

        logger.info(
            "Run #%d complete. %d parcels remaining. "
            "Waiting %ds for ECPA window to reset.",
            run_number, remaining, wait,
        )
        time.sleep(wait)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Unattended Escambia CAMA scraper wrapper."
    )
    parser.add_argument(
        "--wait", type=int, default=DEFAULT_WAIT,
        help=f"Seconds to wait after soft block before restarting "
             f"(default: {DEFAULT_WAIT})",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Pass --dry-run to the scraper (no DB writes).",
    )
    args = parser.parse_args()
    run(wait=args.wait, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
