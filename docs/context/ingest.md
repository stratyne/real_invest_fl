# Project Penstock - context/ingest.md
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

Escambia backfill (already applied 2026-05-04 - do not re-run):
  UPDATE properties SET dor_uc = LPAD(TRIM(dor_uc), 3, '0')
  WHERE county_fips = '12033' AND dor_uc IS NOT NULL
  AND LENGTH(TRIM(dor_uc)) < 3;

## CRS Handling

- CRS detection is per-county at runtime via gdf.crs
- COUNTY_REGISTRY stores confirmed CRS for documentation only
- gdf.crs.to_epsg() is authoritative - not the raw .prj text
- Santa Rosa confirmed EPSG:2883 (raw .prj text incorrectly suggested EPSG:2881)

## Florida Bounding Box (centroid sanity checks)

FL_LAT_MIN = 24.4   FL_LAT_MAX = 31.1
FL_LON_MIN = -87.65  FL_LON_MAX = -80.0
Western boundary is -87.65 (confirmed against 18 Escambia parcels, Perdido River).

## ROOT Path Bootstrap Rules

| File location | ROOT expression |
|---|---|
| scripts/*.py | Path(__file__).resolve().parent.parent |
| real_invest_fl/ingest/*.py | Path(__file__).resolve().parent.parent.parent |
| real_invest_fl/scrapers/*.py | Path(__file__).resolve().parent.parent.parent |
| real_invest_fl/ingest/staging_parsers/*.py | Path(__file__).resolve().parent.parent.parent.parent |

Standard bootstrap block:

    ROOT = Path(__file__).resolve().parent.parent.parent  # adjust per table
    sys.path.insert(0, str(ROOT))
    from config.settings import settings
    from sqlalchemy import create_engine, text
    engine = create_engine(settings.sync_database_url)

## Special Cases

- Miami-Dade: two shapefiles (main + condos)
- Saint Johns: condos zip contained .dbf only - no .shp, no action required

## COUNTY_REGISTRY

Currently duplicated in nal_ingest.py and gis_ingest.py.
Consolidation into a shared module is a pending item (item 18).
Do not consolidate until explicitly assigned - do not touch during other work.

## Ingest Pipeline Rules (never override)

- Filters are query-time only. NEVER apply filter criteria at ingest time.
  Every parcel from every county NAL is written as-is.
- --county-fips is a required CLI arg for both nal_ingest.py and gis_ingest.py.
- mqi_qualified is set to false for all rows at ingest - it is a POC artifact
  and will be removed in a future migration.
  
## Host-Side DB Session Pattern

nal_ingest.py runs on the Windows host, not inside the Docker network.
settings.database_url uses the Docker service name 'db' as the hostname -
unreachable from the host. nal_ingest.py therefore does NOT import
AsyncSessionLocal from real_invest_fl.db.session.

Instead it constructs its own engine and session factory using
settings.host_database_url (localhost:5432), which is reachable from
the host:

    _host_engine = create_async_engine(settings.host_database_url, ...)
    _HostSessionLocal = async_sessionmaker(_host_engine, ...)

This is the same pattern used by the CAMA scrapers (cama/base.py).
Any future host-side ingest script must follow this pattern.
gis_ingest.py uses the sync pattern (settings.host_sync_database_url)
and is unaffected - verify before adding any new async session usage
to gis_ingest.py.

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

## Sale History Scraping

parcel_sale_history is populated by county PA scrapers, not NAL ingest.

Santa Rosa: real_invest_fl/ingest/sales/santa_rosa_sales.py
    Source: https://srcpa.gov/parcel?id={parcel_id}
    Full sale history - all transactions, instrument_type included.
    Parcelcard truncates at 2 - do not use for sale history.
    Quarterly cadence. Resumable via --resume-from {parcel_id}.

Escambia: real_invest_fl/ingest/cama/escambia.py (parse_sales)
    Source: https://www.escpa.org/CAMA/Detail_a.aspx?s={parcel_id}
    Full sale history - instrument_type populated, qualification_code absent.
    Runs as part of CAMA enrichment. Quarterly re-scrape via --force.

Known gaps:
    Santa Rosa: 57,987 parcels capped at 2 sales (parcelcard truncation).
    Backfill via santa_rosa_sales.py - item 124.
    Both counties: sale_yr1 NULL for 82%+ SFR - use parcel_sale_history
    for years_since_last_sale computation, not NAL embedded fields.
	
## Annual Maintenance Dependencies

| Task | Trigger | Script |
|---|---|---|
| Absentee owner recompute | After each annual NAL re-ingest | compute_absentee_owner.py --county-fips {fips} |
| ARV re-run | After quarterly sale history update | arv_calculator.py --county-fips {fips} --force |
| Santa Rosa sale history | Quarterly | santa_rosa_sales.py |
| Escambia sale history | Quarterly (part of CAMA re-run) | run_escambia_cama.py --force |
| NAL refresh | Annual (FL DOR release) | nal_ingest.py --county-fips {fips} |
| CAMA refresh | Annual or as needed | Per-county scraper |
| enrich_missing_spatial_attrs | Once per county at onboarding -- not recurring | enrich_missing_spatial_attrs.py --county-fips {fips} --dor-uc 001 |
| compute_absentee_owner | Once per county at onboarding, then after every NAL re-ingest | compute_absentee_owner.py --county-fips {fips} |

