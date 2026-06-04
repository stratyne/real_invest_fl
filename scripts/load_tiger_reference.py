#!/usr/bin/env python3
"""
load_tiger_reference.py

Downloads Census TIGER/Line boundary files and loads them into permanent
PostGIS reference tables (tiger_zcta, tiger_places) in real_invest_fl.

Usage:
    python scripts/load_tiger_reference.py
    python scripts/load_tiger_reference.py --year 2025
    python scripts/load_tiger_reference.py --year 2025 --force-download

Annual maintenance: Re-run each October after Census September release.
ZCTA boundaries are stable until 2030 -- re-running is safe but optional
for ZCTA until then. Places boundaries update annually.

Uses sync DB session (settings.sync_database_url) per project convention.
"""

import argparse
import sys
from pathlib import Path
from zipfile import ZipFile

import geopandas as gpd
import requests
from sqlalchemy import create_engine, text

# ---------------------------------------------------------------------------
# Path resolution - project root is two levels up from this script
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
TIGER_ROOT = PROJECT_ROOT / "data" / "raw" / "reference" / "tiger"
ZCTA_DIR = TIGER_ROOT / "zcta"
PLACES_DIR = TIGER_ROOT / "places"

# ---------------------------------------------------------------------------
# TIGER/Line URLs - parameterised by year
# ---------------------------------------------------------------------------
ZCTA_URL_TEMPLATE = (
    "https://www2.census.gov/geo/tiger/TIGER{year}/ZCTA520/"
    "tl_{year}_us_zcta520.zip"
)
PLACES_URL_TEMPLATE = (
    "https://www2.census.gov/geo/tiger/TIGER{year}/PLACE/"
    "tl_{year}_12_place.zip"  # 12 = Florida state FIPS
)

TARGET_CRS = "EPSG:4326"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ensure_dirs() -> None:
    ZCTA_DIR.mkdir(parents=True, exist_ok=True)
    PLACES_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[dirs] Staged under {TIGER_ROOT}")


def download_file(url: str, dest_zip: Path, force: bool) -> None:
    if dest_zip.exists() and not force:
        print(f"[download] Already present, skipping: {dest_zip.name}")
        return
    print(f"[download] Fetching {url}")
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        downloaded = 0
        with open(dest_zip, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded / total * 100
                    print(f"\r  {pct:.1f}%", end="", flush=True)
    print(f"\n[download] Saved to {dest_zip}")


def extract_zip(zip_path: Path, dest_dir: Path) -> None:
    print(f"[extract] {zip_path.name} -> {dest_dir}")
    with ZipFile(zip_path, "r") as z:
        z.extractall(dest_dir)


def find_shapefile(directory: Path) -> Path:
    shapefiles = list(directory.glob("*.shp"))
    if not shapefiles:
        raise FileNotFoundError(f"No .shp file found in {directory}")
    if len(shapefiles) > 1:
        raise ValueError(
            f"Multiple .shp files found in {directory}: {shapefiles}"
        )
    return shapefiles[0]


def load_table(
    gdf: gpd.GeoDataFrame,
    table_name: str,
    engine,
) -> int:
    print(f"[db] Loading {len(gdf):,} rows into {table_name} (replace)")
    gdf.to_postgis(
        name=table_name,
        con=engine,
        if_exists="replace",
        index=False,
    )
    return len(gdf)


# ---------------------------------------------------------------------------
# ZCTA
# ---------------------------------------------------------------------------

def process_zcta(year: int, force: bool, engine) -> None:
    url = ZCTA_URL_TEMPLATE.format(year=year)
    zip_path = ZCTA_DIR / f"tl_{year}_us_zcta520.zip"
    shp_dir = ZCTA_DIR / f"tl_{year}_us_zcta520"

    download_file(url, zip_path, force)

    if not shp_dir.exists() or force:
        extract_zip(zip_path, shp_dir)

    shp_path = find_shapefile(shp_dir)
    print(f"[zcta] Reading {shp_path.name}")
    gdf = gpd.read_file(shp_path)

    # Reproject to EPSG:4326 if needed
    if gdf.crs is None or gdf.crs.to_epsg() != 4326:
        print(f"[zcta] Reprojecting from {gdf.crs} to {TARGET_CRS}")
        gdf = gdf.to_crs(TARGET_CRS)

    # Retain only the columns we need
    gdf = gdf[["ZCTA5CE20", "geometry"]].rename(
        columns={"ZCTA5CE20": "zcta5"}
    )

    count = load_table(gdf, "tiger_zcta", engine)
    print(f"[zcta] {count:,} rows loaded.")


# ---------------------------------------------------------------------------
# Places (Florida only - state FIPS 12)
# ---------------------------------------------------------------------------

def process_places(year: int, force: bool, engine) -> None:
    url = PLACES_URL_TEMPLATE.format(year=year)
    zip_path = PLACES_DIR / f"tl_{year}_12_place.zip"
    shp_dir = PLACES_DIR / f"tl_{year}_12_place"

    download_file(url, zip_path, force)

    if not shp_dir.exists() or force:
        extract_zip(zip_path, shp_dir)

    shp_path = find_shapefile(shp_dir)
    print(f"[places] Reading {shp_path.name}")
    gdf = gpd.read_file(shp_path)

    if gdf.crs is None or gdf.crs.to_epsg() != 4326:
        print(f"[places] Reprojecting from {gdf.crs} to {TARGET_CRS}")
        gdf = gdf.to_crs(TARGET_CRS)

    # Retain only the columns we need
    gdf = gdf[["STATEFP", "PLACEFP", "NAME", "geometry"]].rename(
        columns={
            "STATEFP": "statefp",
            "PLACEFP": "placefp",
            "NAME":    "name",
        }
    )

    count = load_table(gdf, "tiger_places", engine)
    print(f"[places] {count:,} rows loaded.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download and load Census TIGER reference tables."
    )
    parser.add_argument(
        "--year",
        type=int,
        default=2025,
        help="TIGER/Line vintage year (default: 2025)",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Re-download zip files even if already present on disk.",
    )
    args = parser.parse_args()

    # Import settings here so the script can be run from the repo root
    # with the venv active without modifying PYTHONPATH manually.
    try:
        sys.path.insert(0, str(PROJECT_ROOT))
        from config.settings import settings
    except ImportError as e:
        print(f"[error] Could not import settings: {e}")
        print("  Ensure you are running from the repo root with the venv active.")
        sys.exit(1)

    engine = create_engine(settings.host_sync_database_url)

    ensure_dirs()
    process_zcta(args.year, args.force_download, engine)
    process_places(args.year, args.force_download, engine)

    print("\n[done] TIGER reference tables loaded successfully.")
    print("  Run scripts/enrich_missing_spatial_attrs.py to apply enrichment.")


if __name__ == "__main__":
    main()
