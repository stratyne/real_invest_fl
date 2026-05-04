# Project Penstock — context/cama.md
# Paste this alongside AGENTS.md when working on CAMA ingest.
# Last updated: 2026-05-04

## File Paths

real_invest_fl/ingest/cama/
  base.py           -- shared framework, no county-specific logic
  escambia.py       -- Escambia County scraper
  santa_rosa.py     -- Santa Rosa County scraper
  __init__.py       -- package marker
real_invest_fl/ingest/cama_ingest.py  -- retained; do not delete until Escambia confirmed

## Run Commands

# Santa Rosa
python -m real_invest_fl.ingest.cama.santa_rosa [options]

# Escambia (DO NOT RUN — escpa.org is DOWN as of 2026-05-04)
python -m real_invest_fl.ingest.cama.escambia [options]
# When site returns: verify with --limit 5 --dry-run before any live run.

## Escambia CAMA Detail

- Source: escpa.org (DOWN as of 2026-05-04)
- Target: dor_uc = '001', ~106,372 parcels
- Beds/baths NOT available from ECPA CAMA detail page
- Sale history NOT available from ECPA CAMA detail page
  (captured via escambia_taxdeed_clerk.py and staging parsers)
- Previous run wrote zoning to 1,399 parcels (dor_uc = '001') but
  cama_enriched_at was never set — confirmed via DB inspection 2026-05-02.
  All remaining CAMA fields are NULL for those 1,399 parcels.
  Full re-scrape of all 106,372 dor_uc = '001' parcels required when site returns.
- Rate limits: DEFAULT_DELAY=1.5, DEFAULT_DELAY_MAX=4.0,
  REST_EVERY=100, REST_SECONDS=270.0

## Santa Rosa CAMA Detail

- Source: https://parcelview.srcpa.gov/?parcel={parcel_id}&baseUrl=http://srcpa.gov/
- Server-rendered HTML. No JavaScript, auth, or cookies required.
- No robots.txt on srcpa.gov or parcelview.srcpa.gov.
- Target: dor_uc = '001', 68,312 parcels
- Status: 3,518 / 68,312 enriched as of 2026-05-04. Run in progress.
- Estimated remaining: ~42 hours at current settings.
- Rate limits: DEFAULT_DELAY=1.0, DEFAULT_DELAY_MAX=3.0,
  REST_EVERY=500, REST_SECONDS=300.0
- Soft-block confirmed at ~2,859 requests over ~1h54m at 1.0–3.0s delay
  with no rest pauses — those were the exact conditions under which it
  triggered. REST_EVERY=500/REST_SECONDS=300.0 added as mitigation.

### Santa Rosa Page Structure
- Valid page marker: presence of 'residentialBuildingsContainer' in response body
- Soft-block signature: HTTP 200 with disclaimer-only body
  (residentialBuildingsContainer absent). Scraper stops cleanly on detection.
- Building data: parsed from data-cell attribute pattern — no regex, no sibling traversal
- Sales data: salesContainer div, same data-cell pattern
- Zoning: zoningContainer div, Code cell
- Sale history captured from same parcelview page per request
- parcel_sale_history populated with full ownership chain per parcel

### Santa Rosa Run Resumability
- cama_enriched_at IS NULL filter skips already-processed parcels automatically.
- Run is fully resumable after any stop (soft-block or manual).

## base.py Design Rules (never override)

- coerce_building() returns (coerced: dict, null_cols: set[str])
  - null_cols: columns explicitly rejected by sanity guards
  - write_cama() writes NULL for these regardless of existing DB value
  - Absent/unparseable fields return None and are silently skipped
- write_cama() never overwrites a good DB value with None from a failed parse,
  but DOES overwrite with NULL for guard-rejected values
- All rate-limiting parameters are county-supplied. base.py has NO defaults.
  County module must declare: DEFAULT_DELAY, DEFAULT_DELAY_MAX,
  REST_EVERY (None = no rest pauses), REST_SECONDS
- target_dor_ucs is county-supplied. Never hardcoded in base.py.
- Soft-block sentinel: base.SOFT_BLOCK = "__SOFT_BLOCK__"
  - County fetch_page() returns this string to stop the run cleanly
  - Returning None skips the parcel and continues the run

## County Module Contract

Each county module must supply:
  COUNTY_FIPS, SOURCE_NAME, HEADERS, TARGET_DOR_UCS,
  DEFAULT_DELAY, DEFAULT_DELAY_MAX, REST_EVERY, REST_SECONDS,
  fetch_page(), parse_building(), parse_sales()

## New County Checklist

1. Check robots.txt at county PA domain
2. Inspect parcel page HTML structure
3. Determine rate limit empirically (start conservative)
4. Create real_invest_fl/ingest/cama/{county_snake}.py
5. Add to COUNTY_REGISTRY in nal_ingest.py and gis_ingest.py

## CAMA Properties Columns

foundation_type      VARCHAR(100)  nullable
exterior_wall        VARCHAR(100)  nullable
roof_type            VARCHAR(100)  nullable
bedrooms             INTEGER       nullable
bathrooms            NUMERIC(4,1)  nullable
bed_bath_source      VARCHAR(50)   nullable
cama_quality_code    VARCHAR(10)   nullable
cama_condition_code  VARCHAR(10)   nullable
cama_enriched_at     TIMESTAMPTZ   nullable
raw_cama_json        JSONB         nullable