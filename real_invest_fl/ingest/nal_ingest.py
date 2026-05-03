# real_invest_fl/ingest/nal_ingest.py
"""
NAL ingest pipeline — Stage 1.

Reads the NAL CSV file for a given county, maps every parcel, and
upserts the entire county inventory into the properties table.

No filter profile is consulted at ingest time. Every parcel from
every county NAL is written as-is. Filtering is exclusively a
query-time operation (Phase 4). mqi_qualified is set to False and
mqi_rejection_reasons is set to NULL on every upserted row — these
are neutral placeholder values, not filter decisions.

File paths are resolved programmatically from the canonical folder
structure:
    data/raw/counties/{fips}_{snake_name}/nal/NAL*.csv

Usage:
    python -m real_invest_fl.ingest.nal_ingest --county-fips 12033
    python -m real_invest_fl.ingest.nal_ingest --county-fips 12113
    python -m real_invest_fl.ingest.nal_ingest --county-fips 12033 --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from real_invest_fl.db.models.property import Property
from real_invest_fl.db.session import AsyncSessionLocal, engine
from real_invest_fl.ingest.nal_mapper import map_nal_row
from real_invest_fl.ingest.run_context import IngestRunContext
from real_invest_fl.utils.logging_setup import configure_logging

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# Constants                                                            #
# ------------------------------------------------------------------ #
CHUNK_SIZE = 400
NAL_DTYPES = str

# Root of the repo — two levels above this file
# real_invest_fl/ingest/nal_ingest.py  →  ../../  →  repo root
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_COUNTIES_DIR = _REPO_ROOT / "data" / "raw" / "counties"

# Florida bounding box for centroid sanity checks (used in GIS ingest,
# referenced here only as documentation of the shared convention).
FL_LAT_MIN, FL_LAT_MAX = 24.4, 31.1
FL_LON_MIN, FL_LON_MAX = -87.6, -80.0


# ------------------------------------------------------------------ #
# County registry                                                      #
# ------------------------------------------------------------------ #
# Maps FIPS → county name exactly as it appears in the folder name
# snake_name formula: name.lower().replace('-','_').replace(' ','_')
# Add counties here as their NAL files are staged for ingest.
COUNTY_REGISTRY: dict[str, str] = {
    "12033": "Escambia",
    "12113": "Santa Rosa",
}


def _snake_name(county_name: str) -> str:
    """Return the canonical snake_name for a county display name."""
    return county_name.lower().replace("-", "_").replace(" ", "_")


def _resolve_nal_path(county_fips: str) -> Path:
    """
    Resolve the NAL CSV path for *county_fips* using the canonical
    folder structure.

    Raises:
        KeyError: FIPS code is not in COUNTY_REGISTRY.
        FileNotFoundError: No NAL*.csv file found in the expected directory.
    """
    if county_fips not in COUNTY_REGISTRY:
        raise KeyError(
            f"County FIPS '{county_fips}' is not registered in COUNTY_REGISTRY. "
            "Add it before running ingest."
        )

    name = COUNTY_REGISTRY[county_fips]
    folder_name = f"{county_fips}_{_snake_name(name)}"
    nal_dir = _COUNTIES_DIR / folder_name / "nal"

    try:
        nal_file = next(nal_dir.glob("NAL*.csv"))
    except StopIteration:
        raise FileNotFoundError(
            f"No NAL*.csv file found in {nal_dir}. "
            "Confirm the file has been staged before running ingest."
        )

    return nal_file


# ------------------------------------------------------------------ #
# Main pipeline                                                        #
# ------------------------------------------------------------------ #

async def run_nal_ingest(county_fips: str, dry_run: bool = False) -> None:
    """
    Execute NAL Stage 1 ingest for *county_fips*.

    Every parcel in the NAL is written to properties regardless of
    use code, assessed value, or any other criterion. No filter profile
    is consulted. mqi_qualified is set to False and
    mqi_rejection_reasons is set to NULL on every row — neutral
    placeholder values pending the query-time filter implementation
    in Phase 4.

    Args:
        county_fips: Five-digit FIPS string, e.g. "12033".
        dry_run: If True, process all records and log counts but do
                 not write anything to the database.
    """
    configure_logging(settings.log_level)

    if dry_run:
        logger.info("DRY RUN mode — no database writes will occur")

    nal_file = _resolve_nal_path(county_fips)
    logger.info(
        "NAL ingest starting | county_fips=%s file=%s",
        county_fips,
        nal_file,
    )

    async with AsyncSessionLocal() as session:

        async with IngestRunContext(
            session=session,
            run_type="NAL",
            county_fips=county_fips,
            source_file=nal_file.name,
            filter_profile_id=None,
        ) as run:

            chunk_num = 0

            for chunk in pd.read_csv(
                nal_file,
                dtype=NAL_DTYPES,
                chunksize=CHUNK_SIZE,
                low_memory=False,
                na_filter=True,
                keep_default_na=True,
            ):
                chunk_num += 1
                rows = chunk.where(pd.notna(chunk), None).to_dict("records")

                upsert_batch: list[dict] = []

                for row in rows:
                    mapped = map_nal_row(
                        row=row,
                        county_fips=county_fips,
                        absentee_owner=None,  # absentee flag deferred to Phase 4
                    )

                    if not mapped.get("parcel_id"):
                        run.increment("skipped")
                        continue

                    # Neutral MQI values — not a filter decision.
                    # These columns will be removed in a future migration once
                    # the query-time filter (Phase 4) is live.
                    mapped["mqi_qualified"] = False
                    mapped["mqi_stage"] = "NAL"
                    mapped["mqi_rejection_reasons"] = None
                    mapped["mqi_qualified_at"] = None

                    mapped["nal_ingested_at"] = datetime.now(tz=timezone.utc)

                    mapped["raw_nal_json"] = {
                        k: v for k, v in row.items() if v is not None
                    }

                    upsert_batch.append(mapped)
                    run.increment("inserted")

                if upsert_batch and not dry_run:
                    await _upsert_batch(session, upsert_batch)

                logger.info(
                    "Chunk %d processed | "
                    "read=%d inserted=%d skipped=%d",
                    chunk_num,
                    run.records_read,
                    run.records_inserted,
                    run.records_skipped,
                )

            logger.info(
                "NAL ingest complete | county_fips=%s "
                "total_read=%d inserted=%d skipped=%d",
                county_fips,
                run.records_read,
                run.records_inserted,
                run.records_skipped,
            )

    await engine.dispose()


# ------------------------------------------------------------------ #
# Database helpers                                                     #
# ------------------------------------------------------------------ #

async def _upsert_batch(
    session: AsyncSession,
    batch: list[dict],
) -> None:
    """
    PostgreSQL INSERT ... ON CONFLICT DO UPDATE (upsert).
    Conflict target: (county_fips, parcel_id).
    Automatically splits batch if parameter count would exceed
    asyncpg's 32767 limit.
    """
    if not batch:
        return

    # Calculate safe batch size based on actual column count
    num_cols = len(batch[0])
    max_rows = 32767 // num_cols   # floor division — stay under limit
    safe_size = min(max_rows - 10, len(batch))  # 10-row safety margin

    sub_batches = [
        batch[i : i + safe_size]
        for i in range(0, len(batch), safe_size)
    ]

    for sub_batch in sub_batches:
        stmt = pg_insert(Property).values(sub_batch)

        update_cols = {
            col.name: stmt.excluded[col.name]
            for col in Property.__table__.columns
            if col.name not in ("county_fips", "parcel_id", "created_at")
        }

        stmt = stmt.on_conflict_do_update(
            index_elements=["county_fips", "parcel_id"],
            set_=update_cols,
        )

        await session.execute(stmt)
        await session.flush()


# ------------------------------------------------------------------ #
# CLI entry point                                                      #
# ------------------------------------------------------------------ #

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Penstock NAL Stage 1 ingest pipeline"
    )
    parser.add_argument(
        "--county-fips",
        required=True,
        metavar="FIPS",
        help="Five-digit county FIPS code (e.g. 12033 for Escambia, "
             "12113 for Santa Rosa).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Process records and log counts without writing to the database.",
    )
    args = parser.parse_args()
    asyncio.run(run_nal_ingest(county_fips=args.county_fips, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
