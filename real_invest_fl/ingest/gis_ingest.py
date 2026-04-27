"""
real_invest_fl/ingest/gis_ingest.py
------------------------------------
GIS shapefile ingest pipeline — Stage 3.

Reads the Escambia County parcel shapefile, reprojects from EPSG:2883
(Florida West State Plane, feet) to EPSG:4326 (WGS84), computes the
centroid of each parcel polygon, and writes the following columns back
to the properties table for every parcel that exists in both the
shapefile and the database:

    geom        — PostGIS POINT geometry in EPSG:4326 (WKT via ST_GeomFromText)
    latitude    — NUMERIC, centroid latitude (decimal degrees)
    longitude   — NUMERIC, centroid longitude (decimal degrees)

Matching is performed on PARCEL_ID (shapefile) = parcel_id (properties).
Only parcels already present in the properties table are updated —
no new rows are inserted.

Usage:
    python -m real_invest_fl.ingest.gis_ingest [--dry-run] [--batch-size N]

Options:
    --dry-run       Parse and reproject but do not write to database.
    --batch-size N  Number of parcels to upsert per transaction (default: 500).

ETHICAL / LEGAL NOTICE:
    Source data is the Escambia County 2025 parcel shapefile, a public
    government dataset. No scraping or rate limiting is required.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Iterator

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
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
logger = logging.getLogger("gis_ingest")

# ── constants ─────────────────────────────────────────────────────────────────
SHP_PATH = (
    ROOT
    / "data"
    / "raw"
    / "gis"
    / "escambia_2025Ppar"
    / "escambia_2025Ppar.shp"
)

SOURCE_CRS  = "EPSG:2883"   # Florida West State Plane (feet) — confirmed from .prj
TARGET_CRS  = "EPSG:4326"   # WGS84 — matches properties.geom SRID
PARCEL_COL  = "PARCEL_ID"   # Shapefile column that maps to properties.parcel_id
DEFAULT_BATCH = 500


# ── chunked iterator ──────────────────────────────────────────────────────────

def _chunks(lst: list, size: int) -> Iterator[list]:
    """Yield successive chunks of `size` from `lst`."""
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


# ── core ingest ───────────────────────────────────────────────────────────────

def run_gis_ingest(dry_run: bool, batch_size: int) -> None:
    """
    Full GIS ingest pipeline.

    Steps:
        1. Load shapefile into GeoDataFrame.
        2. Validate and reproject to EPSG:4326.
        3. Compute centroid for each polygon.
        4. Load all parcel_id values from properties table.
        5. Inner-join shapefile parcels to DB parcels on PARCEL_ID.
        6. Batch-upsert geom, latitude, longitude for matched parcels.
        7. Log summary.
    """
    t_start = time.time()

    # ── Step 1 — Load shapefile ───────────────────────────────────────────── #
    logger.info("Loading shapefile: %s", SHP_PATH)
    if not SHP_PATH.exists():
        logger.error("Shapefile not found at %s — aborting", SHP_PATH)
        sys.exit(1)

    gdf = gpd.read_file(SHP_PATH, engine="pyogrio")
    logger.info("Shapefile loaded — %d features, CRS: %s", len(gdf), gdf.crs)

    # ── Step 2 — Validate CRS ────────────────────────────────────────────── #
    if gdf.crs is None:
        logger.warning("Shapefile has no CRS defined — assuming %s", SOURCE_CRS)
        gdf = gdf.set_crs(SOURCE_CRS)

    logger.info("Source CRS confirmed: %s", gdf.crs)

    # ── Step 3 — Compute centroids in projected CRS, then reproject ───────── #
    # Centroid must be computed BEFORE reprojecting to geographic CRS (4326).
    # Computing centroids in a projected CRS (feet/meters) is mathematically
    # correct. Computing in a geographic CRS (degrees) produces a UserWarning
    # and is inaccurate for large polygons.
    logger.info("Computing centroids in source CRS (%s)...", SOURCE_CRS)
    gdf["centroid_proj"] = gdf.geometry.centroid

    # Validate — flag any null centroids
    null_geom = gdf["centroid_proj"].isnull().sum()
    if null_geom > 0:
        logger.warning("%d features have null geometry — they will be skipped", null_geom)
        gdf = gdf[gdf["centroid_proj"].notnull()].copy()

    # Build a GeoSeries of centroid points and reproject to WGS84
    centroids_proj = gpd.GeoSeries(gdf["centroid_proj"], crs=SOURCE_CRS)
    centroids_wgs84 = centroids_proj.to_crs(TARGET_CRS)
    gdf["centroid"] = centroids_wgs84

    gdf["longitude"] = gdf["centroid"].x
    gdf["latitude"]  = gdf["centroid"].y

    logger.info("Centroids reprojected to %s", TARGET_CRS)

    # Sanity check — Escambia County bounds
    bad_lat = ((gdf["latitude"] < 30.0) | (gdf["latitude"] > 31.0)).sum()
    bad_lon = ((gdf["longitude"] < -88.0) | (gdf["longitude"] > -86.5)).sum()
    if bad_lat > 0:
        logger.warning("%d features have suspicious latitude values", bad_lat)
    if bad_lon > 0:
        logger.warning("%d features have suspicious longitude values", bad_lon)

    # ── Step 4 — Load DB parcel IDs ───────────────────────────────────────── #
    logger.info("Connecting to database...")
    engine = create_engine(settings.sync_database_url, echo=False)

    with engine.connect() as conn:
        result = conn.execute(text("SELECT parcel_id FROM properties"))
        db_parcel_ids = set(r[0] for r in result.fetchall())

    logger.info("Database contains %d parcel records", len(db_parcel_ids))

    # ── Step 5 — Inner join shapefile to DB parcels ───────────────────────── #
    # Keep only shapefile rows whose PARCEL_ID exists in the DB
    gdf[PARCEL_COL] = gdf[PARCEL_COL].astype(str).str.strip()

    matched = gdf[gdf[PARCEL_COL].isin(db_parcel_ids)].copy()
    unmatched_count = len(gdf) - len(matched)

    logger.info(
        "Shapefile: %d total | %d matched to DB | %d unmatched (not in properties table)",
        len(gdf), len(matched), unmatched_count,
    )

    if matched.empty:
        logger.error("No shapefile parcels matched any DB parcel — aborting")
        sys.exit(1)

    # Build the update payload
    # WKT for PostGIS: POINT(lon lat) — note X=longitude, Y=latitude
    matched["geom_wkt"] = matched["centroid"].apply(
        lambda pt: f"POINT({pt.x} {pt.y})"
    )

    update_rows = matched[[PARCEL_COL, "latitude", "longitude", "geom_wkt"]].copy()
    update_rows = update_rows.rename(columns={PARCEL_COL: "parcel_id"})
    update_rows = update_rows.reset_index(drop=True)

    logger.info("Prepared %d rows for upsert", len(update_rows))

    if dry_run:
        logger.info("[DRY-RUN] Sample of first 5 rows that would be written:")
        for _, row in update_rows.head(5).iterrows():
            logger.info(
                "  parcel_id=%-20s lat=%.6f lon=%.6f geom=%s",
                row["parcel_id"], row["latitude"], row["longitude"], row["geom_wkt"],
            )
        logger.info("[DRY-RUN] No data written to database.")
        return

    # ── Step 6 — Batch upsert ─────────────────────────────────────────────── #
    rows_list = update_rows.to_dict(orient="records")
    total_batches = (len(rows_list) + batch_size - 1) // batch_size
    total_updated = 0

    logger.info(
        "Writing to database in %d batches of up to %d rows — "
        "each batch commits independently...",
        total_batches, batch_size,
    )

    update_sql = text("""
        UPDATE properties
        SET
            geom      = ST_GeomFromText(:geom_wkt, 4326),
            latitude  = :latitude,
            longitude = :longitude,
            updated_at = NOW()
        WHERE parcel_id = :parcel_id
    """)

    for batch_num, batch in enumerate(_chunks(rows_list, batch_size), start=1):
        # Each batch is its own transaction — released immediately after commit.
        # This prevents long-held locks from blocking concurrent writers
        # such as the CAMA scraper.
        with engine.begin() as conn:
            conn.execute(update_sql, batch)
        total_updated += len(batch)

        if batch_num % 10 == 0 or batch_num == total_batches:
            elapsed = time.time() - t_start
            pct = total_updated / len(rows_list) * 100
            logger.info(
                "Batch %d/%d — %d rows written (%.1f%%) — %.1fs elapsed",
                batch_num, total_batches, total_updated, pct, elapsed,
            )

    # ── Step 7 — Summary ─────────────────────────────────────────────────── #
    elapsed = time.time() - t_start
    logger.info(
        "GIS ingest complete | matched=%d updated=%d unmatched=%d duration=%.1fs",
        len(matched), total_updated, unmatched_count, elapsed,
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest Escambia County parcel shapefile into properties table."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Parse and reproject but do not write to the database.",
    )
    parser.add_argument(
        "--batch-size", type=int, default=DEFAULT_BATCH,
        help=f"Rows per transaction batch (default: {DEFAULT_BATCH}).",
    )
    args = parser.parse_args()

    run_gis_ingest(dry_run=args.dry_run, batch_size=args.batch_size)


if __name__ == "__main__":
    main()
