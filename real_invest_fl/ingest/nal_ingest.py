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
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from real_invest_fl.db.models.property import Property
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from real_invest_fl.ingest.nal_mapper import map_nal_row
from real_invest_fl.ingest.nal_filter import _is_absentee as _compute_absentee_raw
from real_invest_fl.ingest.run_context import IngestRunContext
from real_invest_fl.utils.logging_setup import configure_logging

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def _compute_absentee(row: dict) -> bool | None:
    """
    Derive absentee owner flag for a NAL row.

    Returns True if owner mailing address differs from physical address.
    Returns False if addresses are present and match.
    Returns None if neither OWN_ADDR1 nor OWN_ADDR2 yields a usable
    street address — cannot determine residency, store as NULL.

    Option A per DECISIONS.md: NULL when undeterminable.
    """
    own_addr1 = (row.get("OWN_ADDR1") or "").strip()
    own_addr2 = (row.get("OWN_ADDR2") or "").strip()

    # If neither field starts with a digit, no usable street address exists
    if not (
        (own_addr1 and own_addr1[0].isdigit())
        or (own_addr2 and own_addr2[0].isdigit())
    ):
        return None

    return _compute_absentee_raw(row)

# ------------------------------------------------------------------ #
# Host-side DB engine                                                  #
# nal_ingest.py runs on the Windows host, not inside the Docker       #
# network. settings.database_url uses the 'db' service hostname which #
# is unreachable from the host. settings.host_database_url resolves   #
# to localhost:5432 and is required for all host-side scripts.        #
# This mirrors the pattern used by the CAMA scrapers (cama/base.py).  #
# ------------------------------------------------------------------ #
_host_engine = create_async_engine(
    settings.host_database_url,
    echo=False,
    pool_pre_ping=True,
)
_HostSessionLocal = async_sessionmaker(
    _host_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


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

    async with _HostSessionLocal() as session:

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
                        absentee_owner=_compute_absentee(row),
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

        # ------------------------------------------------------------------ #
        # Stamp counties.nal_last_ingested_at                                 #
        # Runs after IngestRunContext has committed the run record.            #
        # Skipped in dry_run mode — no writes occurred so no stamp is valid.  #
        # ------------------------------------------------------------------ #
        if not dry_run:
            async with _HostSessionLocal() as stamp_session:
                await stamp_session.execute(
                    text(
                        "UPDATE counties "
                        "SET nal_last_ingested_at = :now, "
                        "    updated_at = :now "
                        "WHERE county_fips = :fips"
                    ),
                    {
                        "now": datetime.now(tz=timezone.utc),
                        "fips": county_fips,
                    },
                )
                await stamp_session.commit()
            logger.info(
                "counties.nal_last_ingested_at stamped | county_fips=%s",
                county_fips,
            )

    await _host_engine.dispose()


# ------------------------------------------------------------------ #
# Database helpers                                                     #
# ------------------------------------------------------------------ #

# ── NAL upsert column protection ─────────────────────────────────────────
# Columns written by other pipelines that must never be overwritten
# by a NAL re-ingest run. NAL does not own these values.
_NAL_UPSERT_NEVER_OVERWRITE: frozenset[str] = frozenset({
    # GIS ingest
    "geom",
    "latitude",
    "longitude",
    # CAMA ingest
    "tot_lvg_area", # heated area takes precedence over NAL effective area
    "foundation_type",
    "exterior_wall",
    "roof_type",
    "bedrooms",
    "bathrooms",
    "bed_bath_source",
    "cama_quality_code",
    "cama_condition_code",
    "cama_enriched_at",
    "raw_cama_json",
    "zoning",
    # ARV calculator
    "arv_estimate",
    "arv_spread",
    "arv_source",
    "jv_per_sqft",
    # Listing matcher
    "list_price",
    # Phase 2 scoring — not yet built, protect slots
    "seller_probability_score",
    "seller_score_updated_at",
    "permit_count",
    "estimated_rehab_per_sqft",
    # Audit — server_default on insert only; never overwrite
    "created_at",
})


async def _upsert_batch(
    session: AsyncSession,
    batch: list[dict],
) -> None:
    """
    PostgreSQL INSERT ... ON CONFLICT DO UPDATE (upsert).
    Conflict target: (county_fips, parcel_id).

    On conflict, only NAL-owned columns are updated. Columns written
    by GIS ingest, CAMA ingest, the ARV calculator, the listing matcher,
    Phase 2 scoring, and audit timestamps are excluded from the update
    set so that re-running NAL ingest cannot wipe downstream pipeline
    work. See _NAL_UPSERT_NEVER_OVERWRITE.

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
            if col.name not in _NAL_UPSERT_NEVER_OVERWRITE
            and col.name not in ("county_fips", "parcel_id")
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
