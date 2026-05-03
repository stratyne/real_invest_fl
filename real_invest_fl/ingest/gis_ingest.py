# real_invest_fl/ingest/gis_ingest.py
"""
GIS shapefile ingest pipeline — Stage 3.

Reads the parcel shapefile for a given county, reprojects from the
county's source CRS (read from the .prj file) to EPSG:4326 (WGS84),
computes the centroid of each parcel polygon, and writes the following
columns back to the properties table for every parcel that exists in
both the shapefile and the database:

    geom        — PostGIS POINT geometry in EPSG:4326 (WKT via ST_GeomFromText)
    latitude    — NUMERIC, centroid latitude (decimal degrees)
    longitude   — NUMERIC, centroid longitude (decimal degrees)

Matching is performed on PARCEL_ID (shapefile) = parcel_id (properties).
Only parcels already present in the properties table are updated —
no new rows are inserted.

File paths are resolved programmatically from the canonical folder
structure:
    data/raw/counties/{fips}_{snake_name}/gis/*.shp

The source CRS is detected per-county from the .prj file, not assumed
as a compile-time constant. A warning is emitted if the detected CRS
differs from EPSG:2883 (Florida West State Plane, feet), which is
the expected CRS for most Florida counties in this dataset but is NOT
assumed.

Centroid sanity check uses Florida's statewide bounding box
(lat 24.4–31.1, lon -87.6 to -80.0) rather than any county-specific
bounds.

Usage:
    python -m real_invest_fl.ingest.gis_ingest --county-fips 12033
    python -m real_invest_fl.ingest.gis_ingest --county-fips 12113
    python -m real_invest_fl.ingest.gis_ingest --county-fips 12033 --dry-run
    python -m real_invest_fl.ingest.gis_ingest --county-fips 12033 --batch-size 250

Options:
    --county-fips FIPS  Required. Five-digit county FIPS code.
    --dry-run           Parse and reproject but do not write to the database.
    --batch-size N      Number of parcels to update per transaction (default: 500).

ETHICAL / LEGAL NOTICE:
    Source data are Florida county parcel shapefiles, public government
    datasets. No scraping or rate limiting is required.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Iterator

import geopandas as gpd
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
TARGET_CRS    = "EPSG:4326"   # WGS84 — matches properties.geom SRID
PARCEL_COL    = "PARCEL_ID"   # Shapefile column that maps to properties.parcel_id
DEFAULT_BATCH = 500

# Florida statewide bounding box — used for centroid sanity check on
# every county. County-specific bounds are never hardcoded here.
FL_LAT_MIN, FL_LAT_MAX = 24.4, 31.1
FL_LON_MIN, FL_LON_MAX = -87.65, -80.0

# Expected CRS for Florida county shapefiles in this dataset.
# Emits a warning (not an error) when a county's .prj does not match.
EXPECTED_SOURCE_CRS = "EPSG:2883"

# Root data directory
_COUNTIES_DIR = ROOT / "data" / "raw" / "counties"


# Maps FIPS → (display_name, expected_source_crs).
# Most Florida county shapefiles use EPSG:2883 (FL West State Plane, feet).
# Counties in the North or East zones use different EPSG codes — these are
# recorded here as the confirmed CRS read from each county's .prj file.
# The CRS stored here is documentation only. The actual reprojection always
# uses gdf.crs as detected from the .prj at runtime.
COUNTY_REGISTRY: dict[str, tuple[str, str]] = {
    "12033": ("Escambia",   "EPSG:2883"),   # FL West — confirmed
    "12113": ("Santa Rosa", "EPSG:2883"),   # confirmed from gdf.crs.to_epsg()
}


def _snake_name(county_name: str) -> str:
    """Return the canonical snake_name for a county display name."""
    return county_name.lower().replace("-", "_").replace(" ", "_")


def _resolve_shp_path(county_fips: str) -> Path:
    """
    Resolve the shapefile path for *county_fips* using the canonical
    folder structure.

    Shapefiles live flat in the gis/ folder (no subfolder):
        data/raw/counties/{fips}_{snake_name}/gis/*.shp

    Raises:
        KeyError: FIPS code is not in COUNTY_REGISTRY.
        FileNotFoundError: No .shp file found in the expected directory.
    """
    if county_fips not in COUNTY_REGISTRY:
        raise KeyError(
            f"County FIPS '{county_fips}' is not registered in COUNTY_REGISTRY. "
            "Add it before running GIS ingest."
        )

    name, _expected_crs = COUNTY_REGISTRY[county_fips]   # unpack tuple
    folder_name = f"{county_fips}_{_snake_name(name)}"
    gis_dir = _COUNTIES_DIR / folder_name / "gis"

    try:
        shp_file = next(gis_dir.glob("*.shp"))
    except StopIteration:
        raise FileNotFoundError(
            f"No .shp file found in {gis_dir}. "
            "Confirm the shapefile has been staged before running GIS ingest."
        )

    return shp_file


# ── chunked iterator ──────────────────────────────────────────────────────────

def _chunks(lst: list, size: int) -> Iterator[list]:
    """Yield successive chunks of `size` from `lst`."""
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


# ── core ingest ───────────────────────────────────────────────────────────────

def run_gis_ingest(county_fips: str, dry_run: bool, batch_size: int) -> None:
    """
    Full GIS ingest pipeline for *county_fips*.

    Steps:
        1. Resolve shapefile path from canonical folder structure.
        2. Load shapefile into GeoDataFrame.
        3. Detect source CRS from .prj; warn if it differs from EPSG:2883.
        4. Compute centroids in the source (projected) CRS.
        5. Reproject centroids to EPSG:4326.
        6. Sanity-check centroids against Florida's statewide bounding box.
        7. Load all parcel_id values for this county from properties table.
        8. Inner-join shapefile parcels to DB parcels on PARCEL_ID.
        9. Batch-update geom, latitude, longitude for matched parcels.
       10. Log summary.
    """
    t_start = time.time()

    # ── Step 1 — Resolve path ─────────────────────────────────────────────── #
    shp_path = _resolve_shp_path(county_fips)
    _county_name, expected_crs = COUNTY_REGISTRY[county_fips]   # unpack here too

    logger.info(
        "GIS ingest starting | county_fips=%s shapefile=%s",
        county_fips,
        shp_path,
    )

    # ── Step 2 — Load shapefile ───────────────────────────────────────────── #
    if not shp_path.exists():
        logger.error("Shapefile not found at %s — aborting", shp_path)
        sys.exit(1)

    gdf = gpd.read_file(shp_path, engine="pyogrio")
    logger.info("Shapefile loaded — %d features, CRS: %s", len(gdf), gdf.crs)

    # ── Step 3 — Detect and validate source CRS ───────────────────────────── #
    if gdf.crs is None:
        logger.warning(
            "Shapefile has no CRS embedded — falling back to %s. "
            "Verify this is correct for county_fips=%s before proceeding.",
            expected_crs,
            county_fips,
        )
        gdf = gdf.set_crs(expected_crs)

    source_crs = gdf.crs.to_epsg()
    source_crs_str = f"EPSG:{source_crs}" if source_crs else str(gdf.crs)

    if source_crs_str != expected_crs:
        logger.warning(
            "county_fips=%s source CRS is %s, registry expects %s. "
            "Reprojection will proceed using the detected CRS. "
            "If this is a new county, update COUNTY_REGISTRY with the "
            "confirmed CRS from the .prj file.",
            county_fips, source_crs_str, expected_crs,
        )
    else:
        logger.info(
            "Source CRS confirmed: %s (matches registry for county_fips=%s)",
            source_crs_str, county_fips,
        )

    # ── Step 4 — Compute centroids in projected CRS ───────────────────────── #
    # Centroids must be computed BEFORE reprojecting to a geographic CRS
    # (EPSG:4326). Computing centroids in a projected CRS (feet/meters) is
    # mathematically correct. Computing in a geographic CRS (degrees)
    # produces a UserWarning and is inaccurate for large polygons.
    logger.info("Computing centroids in source CRS (%s)...", source_crs_str)
    gdf["centroid_proj"] = gdf.geometry.centroid

    null_geom = gdf["centroid_proj"].isnull().sum()
    if null_geom > 0:
        logger.warning(
            "%d features have null geometry — they will be skipped", null_geom
        )
        gdf = gdf[gdf["centroid_proj"].notnull()].copy()

    # ── Step 5 — Reproject centroids to WGS84 ────────────────────────────── #
    centroids_proj = gpd.GeoSeries(gdf["centroid_proj"], crs=gdf.crs)
    centroids_wgs84 = centroids_proj.to_crs(TARGET_CRS)
    gdf["centroid"] = centroids_wgs84

    gdf["longitude"] = gdf["centroid"].x
    gdf["latitude"]  = gdf["centroid"].y

    logger.info("Centroids reprojected to %s", TARGET_CRS)

    # ── Step 6 — Florida statewide bounding box sanity check ─────────────── #
    # These bounds apply to every Florida county, not any single one.
    bad_lat = (
        (gdf["latitude"] < FL_LAT_MIN) | (gdf["latitude"] > FL_LAT_MAX)
    ).sum()
    bad_lon = (
        (gdf["longitude"] < FL_LON_MIN) | (gdf["longitude"] > FL_LON_MAX)
    ).sum()

    if bad_lat > 0:
        logger.warning(
            "county_fips=%s: %d features have latitude outside Florida "
            "bounds (%.1f – %.1f). Verify shapefile and CRS.",
            county_fips, bad_lat, FL_LAT_MIN, FL_LAT_MAX,
        )
    if bad_lon > 0:
        logger.warning(
            "county_fips=%s: %d features have longitude outside Florida "
            "bounds (%.1f – %.1f). Verify shapefile and CRS.",
            county_fips, bad_lon, FL_LON_MIN, FL_LON_MAX,
        )
    # ── Step 6 diagnostic — log outlier parcel IDs (temporary) ──────────── #
    if bad_lat > 0 or bad_lon > 0:
        outliers = gdf[
            (gdf["latitude"]  < FL_LAT_MIN) | (gdf["latitude"]  > FL_LAT_MAX) |
            (gdf["longitude"] < FL_LON_MIN) | (gdf["longitude"] > FL_LON_MAX)
        ][[PARCEL_COL, "latitude", "longitude"]].copy()
        for _, row in outliers.iterrows():
            logger.warning(
                "  OUTLIER parcel_id=%-20s lat=%.6f lon=%.6f",
                row[PARCEL_COL], row["latitude"], row["longitude"],
            )

    # ── Step 7 — Load DB parcel IDs for this county ───────────────────────── #
    logger.info("Connecting to database...")
    db_engine = create_engine(settings.sync_database_url, echo=False)

    with db_engine.connect() as conn:
        result = conn.execute(
            text("SELECT parcel_id FROM properties WHERE county_fips = :fips"),
            {"fips": county_fips},
        )
        db_parcel_ids = {r[0] for r in result.fetchall()}

    logger.info(
        "Database contains %d parcel records for county_fips=%s",
        len(db_parcel_ids),
        county_fips,
    )

    # ── Step 8 — Inner-join shapefile to DB parcels ───────────────────────── #
    gdf[PARCEL_COL] = gdf[PARCEL_COL].astype(str).str.strip()
    matched = gdf[gdf[PARCEL_COL].isin(db_parcel_ids)].copy()
    unmatched_count = len(gdf) - len(matched)

    logger.info(
        "Shapefile: %d total | %d matched to DB | "
        "%d unmatched (not in properties table)",
        len(gdf), len(matched), unmatched_count,
    )

    if matched.empty:
        logger.error(
            "No shapefile parcels matched any DB parcel for "
            "county_fips=%s — aborting",
            county_fips,
        )
        sys.exit(1)

    # Build the update payload
    # WKT for PostGIS: POINT(lon lat) — note X=longitude, Y=latitude
    matched = matched.copy()
    matched["geom_wkt"] = matched["centroid"].apply(
        lambda pt: f"POINT({pt.x} {pt.y})"
    )

    update_rows = matched[[PARCEL_COL, "latitude", "longitude", "geom_wkt"]].copy()
    update_rows = update_rows.rename(columns={PARCEL_COL: "parcel_id"})
    update_rows = update_rows.reset_index(drop=True)

    logger.info("Prepared %d rows for update", len(update_rows))

    if dry_run:
        logger.info("[DRY-RUN] Sample of first 5 rows that would be written:")
        for _, row in update_rows.head(5).iterrows():
            logger.info(
                "  parcel_id=%-20s lat=%.6f lon=%.6f geom=%s",
                row["parcel_id"],
                row["latitude"],
                row["longitude"],
                row["geom_wkt"],
            )
        logger.info("[DRY-RUN] No data written to database.")
        return

    # ── Step 9 — Batch update ─────────────────────────────────────────────── #
    rows_list = update_rows.to_dict(orient="records")
    total_batches = (len(rows_list) + batch_size - 1) // batch_size
    total_updated = 0

    logger.info(
        "Writing to database in %d batches of up to %d rows — "
        "each batch commits independently...",
        total_batches,
        batch_size,
    )

    update_sql = text("""
        UPDATE properties
        SET
            geom       = ST_GeomFromText(:geom_wkt, 4326),
            latitude   = :latitude,
            longitude  = :longitude,
            updated_at = NOW()
        WHERE parcel_id = :parcel_id
          AND county_fips = :county_fips
    """)

    for batch_num, batch in enumerate(_chunks(rows_list, batch_size), start=1):
        # Bind county_fips into every row so the WHERE clause is unambiguous
        # across multi-county databases.
        for r in batch:
            r["county_fips"] = county_fips

        # Each batch is its own transaction — released immediately after commit.
        # This prevents long-held locks from blocking concurrent writers.
        with db_engine.begin() as conn:
            conn.execute(update_sql, batch)
        total_updated += len(batch)

        if batch_num % 10 == 0 or batch_num == total_batches:
            elapsed = time.time() - t_start
            pct = total_updated / len(rows_list) * 100
            logger.info(
                "Batch %d/%d — %d rows written (%.1f%%) — %.1fs elapsed",
                batch_num, total_batches, total_updated, pct, elapsed,
            )

    # ── Step 10 — Summary ────────────────────────────────────────────────── #
    elapsed = time.time() - t_start
    logger.info(
        "GIS ingest complete | county_fips=%s matched=%d updated=%d "
        "unmatched=%d duration=%.1fs",
        county_fips, len(matched), total_updated, unmatched_count, elapsed,
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Penstock GIS shapefile ingest pipeline — Stage 3."
    )
    parser.add_argument(
        "--county-fips",
        required=True,
        metavar="FIPS",
        help="Five-digit county FIPS code (e.g. 12033 for Escambia, "
             "12113 for Santa Rosa).",
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

    run_gis_ingest(
        county_fips=args.county_fips,
        dry_run=args.dry_run,
        batch_size=args.batch_size,
    )


if __name__ == "__main__":
    main()
