# Project Penstock — context/ingest.md
# Paste this alongside AGENTS.md when working on NAL/GIS ingest pipeline.
# Last updated: 2026-05-04

## Key Files

real_invest_fl/ingest/
  nal_ingest.py     -- NAL CSV ingest, multi-county, --county-fips required
  gis_ingest.py     -- GIS shapefile ingest, multi-county, --county-fips required
  nal_mapper.py     -- column mapping + _dor_uc() normalizer
  nal_filter.py     -- retained for reference; filters are query-time only
  arv_calculator.py -- PENDING REFACTOR (mqi_qualified drift)
  run_context.py    -- shared ingest run context

## Canonical Path Pattern

data/raw/counties/{fips}_{snake_name}/{type}/

snake_name = county_name.lower().replace('-','_').replace(' ','_')

Examples:
  data/raw/counties/12033_escambia/nal/
  data/raw/counties/12033_escambia/gis/
  data/raw/counties/12113_santa_rosa/nal/
  data/raw/counties/12113_santa_rosa/gis/

File discovery (always use globs, never hardcoded filenames):
  NAL: next(nal_dir.glob("NAL*.csv"))
  GIS: next(gis_dir.glob("*.shp"))

## dor_uc Normalization

Florida DOR specifies use codes as three-digit zero-padded strings.
Some county NAL files ship unpadded (Escambia: '1', '2', '93').
nal_mapper.py _dor_uc() normalizes all variants to '001', '002', '093' at ingest.

Escambia backfill (already applied 2026-05-04 — do not re-run):
  UPDATE properties SET dor_uc = LPAD(TRIM(dor_uc), 3, '0')
  WHERE county_fips = '12033' AND dor_uc IS NOT NULL
  AND LENGTH(TRIM(dor_uc)) < 3;

## CRS Handling

- CRS detection is per-county at runtime via gdf.crs
- COUNTY_REGISTRY stores confirmed CRS for documentation only
- gdf.crs.to_epsg() is authoritative — not the raw .prj text
- Santa Rosa confirmed EPSG:2883 (raw .prj text incorrectly suggested EPSG:2881)

## Florida Bounding Box (centroid sanity checks)

FL_LAT_MIN = 24.4   FL_LAT_MAX = 31.1
FL_LON_MIN = -87.65  FL_LON_MAX = -80.0
Western boundary is -87.65 (confirmed against 18 Escambia parcels, Perdido River).

## Special Cases

- Miami-Dade: two shapefiles (main + condos)
- Saint Johns: condos zip contained .dbf only — no .shp, no action required

## COUNTY_REGISTRY

Currently duplicated in nal_ingest.py and gis_ingest.py.
Consolidation into a shared module is a pending item (item 18).
Do not consolidate until explicitly assigned — do not touch during other work.

## Ingest Pipeline Rules (never override)

- Filters are query-time only. NEVER apply filter criteria at ingest time.
  Every parcel from every county NAL is written as-is.
- --county-fips is a required CLI arg for both nal_ingest.py and gis_ingest.py.
- mqi_qualified is set to false for all rows at ingest — it is a POC artifact
  and will be removed in a future migration.

## Staging File-Drop Workflow

| Source | Staging folder | Format | Cadence |
|---|---|---|---|
| LandmarkWeb lis pendens | data/staging/lis_pendens/ | .xlsx | Weekly |
| RealForeclose foreclosures | data/staging/foreclosure/ | .csv (2-col key-value) | Weekly |
| Zillow listings | data/staging/zillow/ | .csv (one value per line) | Weekly |

Run commands:
  python scripts/run_staging_import.py --source lis_pendens
  python scripts/run_staging_import.py --source foreclosure
  python scripts/run_staging_import.py --source zillow

Tax deed data: sourced via direct scraper (run_taxdeed.py), not file-drop.
data/staging/tax_deed/ retained pending Ch. 119 response from Escambia Clerk.

## Staging Folder Structure

data/staging/
  lis_pendens/    -- LandmarkWeb .xlsx, weekly
  foreclosure/    -- RealForeclose .csv (2-col key-value), weekly
  tax_deed/       -- retained pending Ch. 119 response; no active file-drop
  zillow/         -- Zillow .csv (one value per line), weekly
