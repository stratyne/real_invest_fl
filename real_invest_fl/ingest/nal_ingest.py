# real_invest_fl/ingest/nal_ingest.py
"""
NAL ingest pipeline — Stage 1.

Reads the NAL CSV file in chunks, evaluates each parcel against
the active filter profile, and upserts qualifying and non-qualifying
parcels into the properties table.

All parcels in the NAL are written to properties regardless of
whether they pass the filter. Passing parcels get mqi_qualified=True.
Rejected parcels get mqi_qualified=False with rejection reasons logged.
This ensures the MQI is a complete county inventory, not just
the passing subset.

Usage:
    python -m real_invest_fl.ingest.nal_ingest
    python -m real_invest_fl.ingest.nal_ingest --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from real_invest_fl.db.models.filter_profile import FilterProfile
from real_invest_fl.db.models.property import Property
from real_invest_fl.db.session import AsyncSessionLocal, engine
from real_invest_fl.ingest.nal_filter import evaluate_nal, _is_absentee
from real_invest_fl.ingest.nal_mapper import map_nal_row
from real_invest_fl.ingest.run_context import IngestRunContext
from real_invest_fl.utils.logging_setup import configure_logging

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# Constants                                                            #
# ------------------------------------------------------------------ #
NAL_FILE = Path(
    r"D:\Chris\Documents\Stratyne\real_invest_fl\data\raw\NAL27F202502VAB.csv"
)
COUNTY_FIPS = "12033"
FILTER_PROFILE_ID = 1
CHUNK_SIZE = 400

NAL_DTYPES = str


# ------------------------------------------------------------------ #
# Main pipeline                                                        #
# ------------------------------------------------------------------ #

async def run_nal_ingest(dry_run: bool = False) -> None:
    """
    Execute NAL Stage 1 ingest.

    Args:
        dry_run: If True, process all records and log counts but
                 do not write anything to the database.
    """
    configure_logging(settings.log_level)

    if dry_run:
        logger.info("DRY RUN mode — no database writes will occur")

    async with AsyncSessionLocal() as session:

        # ---------------------------------------------------------- #
        # Load filter profile                                          #
        # ---------------------------------------------------------- #
        profile = await _load_filter_profile(session, FILTER_PROFILE_ID)
        if profile is None:
            raise RuntimeError(
                f"Filter profile id={FILTER_PROFILE_ID} not found in database."
            )

        criteria = profile.filter_criteria
        logger.info(
            "Loaded filter profile | id=%d name=%s county_fips=%s",
            profile.id,
            profile.profile_name,
            profile.county_fips,
        )

        # ---------------------------------------------------------- #
        # Open ingest run record                                       #
        # ---------------------------------------------------------- #
        async with IngestRunContext(
            session=session,
            run_type="NAL",
            county_fips=COUNTY_FIPS,
            source_file=NAL_FILE.name,
            filter_profile_id=FILTER_PROFILE_ID,
        ) as run:

            chunk_num = 0

            for chunk in pd.read_csv(
                NAL_FILE,
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
                    absentee = _is_absentee(row)
                    passed, rejections = evaluate_nal(row, criteria)

                    mapped = map_nal_row(
                        row=row,
                        county_fips=COUNTY_FIPS,
                        absentee_owner=absentee,
                    )

                    if not mapped.get("parcel_id"):
                        run.increment("skipped")
                        continue

                    mapped["mqi_qualified"] = passed
                    mapped["mqi_stage"] = "NAL"
                    mapped["mqi_rejection_reasons"] = (
                        rejections if rejections else None
                    )
                    mapped["mqi_qualified_at"] = (
                        datetime.now(tz=timezone.utc) if passed else None
                    )
                    mapped["nal_ingested_at"] = datetime.now(tz=timezone.utc)

                    mapped["raw_nal_json"] = {
                        k: v for k, v in row.items() if v is not None
                    }

                    upsert_batch.append(mapped)

                    if passed:
                        run.increment("inserted")
                    else:
                        run.increment(
                            "rejected",
                            rejection_reason=rejections[0] if rejections else None,
                        )

                if upsert_batch and not dry_run:
                    await _upsert_batch(session, upsert_batch)

                logger.info(
                    "Chunk %d processed | "
                    "read=%d inserted=%d rejected=%d skipped=%d",
                    chunk_num,
                    run.records_read,
                    run.records_inserted,
                    run.records_rejected,
                    run.records_skipped,
                )

            logger.info(
                "NAL ingest complete | "
                "total_read=%d qualified=%d rejected=%d skipped=%d",
                run.records_read,
                run.records_inserted,
                run.records_rejected,
                run.records_skipped,
            )

    await engine.dispose()


# ------------------------------------------------------------------ #
# Database helpers                                                     #
# ------------------------------------------------------------------ #

async def _load_filter_profile(
    session: AsyncSession,
    profile_id: int,
) -> FilterProfile | None:
    result = await session.execute(
        select(FilterProfile).where(FilterProfile.id == profile_id)
    )
    return result.scalar_one_or_none()


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
    max_rows = 32767 // num_cols  # floor division — stay under limit
    safe_size = min(max_rows - 10, len(batch))  # 10-row safety margin

    # Split into safe sub-batches if needed
    sub_batches = [
        batch[i:i + safe_size]
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
        "--dry-run",
        action="store_true",
        help="Process records and log counts without writing to the database",
    )
    args = parser.parse_args()
    asyncio.run(run_nal_ingest(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
