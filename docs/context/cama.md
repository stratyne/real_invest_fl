# Project Penstock — context/cama.md
# Paste this alongside AGENTS.md when working on CAMA ingest.
# Last updated: 2026-05-26

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

# Escambia
python -m real_invest_fl.ingest.cama.escambia [options]
python scripts/run_escambia_cama.py
# Always verify with --limit 5 --dry-run before any live run.

## Escambia CAMA Detail

- Source: https://www.escpa.org/CAMA/Detail_a.aspx?s={parcel_id}
- Site was DOWN 2026-05-04 through approximately 2026-05-24. Restarted 2026-05-26.
- Target: dor_uc = '001', ~106,372 parcels
- Beds/baths NOT available from ECPA CAMA detail page
- Sale history IS available and captured from ECPA CAMA detail page. 
  parse_sales() reads the Sales Data table (ctl00_MasterPlaceHolder_SalesCell).
  Grantor/grantee not available — stored as empty string.
- Parcel ID format: 16-character no-hyphen string (e.g. 182S303000004001)
  confirmed from DB. URL format matches directly — no transformation needed.
- Run via scripts/run_escambia_cama.py for unattended operation — auto-restarts after soft block with 420s wait.
- Rate limits: DEFAULT_DELAY=2.0, DEFAULT_DELAY_MAX=5.0, REST_EVERY=None, REST_SECONDS=0.0
- Search.aspx redirect = parcel absent from ECPA CAMA — logged as warning, skipped cleanly, continues run.
- Sale date parsing: MM/DD/YYYY stored as-is. MM/YYYY normalized to
  date(YYYY, MM, 1) and stored. Unparseable formats logged at DEBUG and skipped.
- eff_yr_blt: captured from "Effective Year" label in building table header.

## Santa Rosa CAMA Detail

- Source: https://parcelcard.srcpa.gov/?parcel={parcel_id}&baseUrl=http://srcpa.gov/
- Previous source (parcelview.srcpa.gov) was replaced — site rebuilt as
  Remix/React SSR application. Confirmed 2026-05-24.
- Server-rendered HTML. No JavaScript, auth, or cookies required.
  Plain httpx GET is sufficient.
- No robots.txt on srcpa.gov or parcelcard.srcpa.gov.
- TARGET: dor_uc = '001', 68,312 parcels
- Status: 7,361 enriched (via old parcelview scraper, data quality verified good).
  60,951 remaining. Run restarted 2026-05-24.
- Rate limits: DEFAULT_DELAY=1.0, DEFAULT_DELAY_MAX=3.0,
  REST_EVERY=500, REST_SECONDS=300.0
- Soft-block confirmed at ~2,859 requests over ~1h54m at 1.0–3.0s delay
  with no rest pauses under old endpoint. REST_EVERY=500/REST_SECONDS=300.0
  retained as mitigation.
- SOURCE_NAME: srcpa_parcelcard (updated from srcpa_parcelview)

### Santa Rosa Page Structure (parcelcard.srcpa.gov)
- Valid response: window.__remixContext present in body with full parcel data
- Soft-block signature: window.__remixContext absent entirely — stop run
- Not-found signature: window.__remixContext present, routes/_index loader
  data has "empty":true — skip parcel cleanly, continue run
- Building fields: two-column <td> bold-label/value grid using Tailwind classes.
  Abbreviated labels: extw, RCVR, fndn, Bath, BED, qual
- Heated area (tot_lvg_area): sourced from remixContext JSON
  path: buildings.units[0].squareFeet.heated
  HTML summary table (code/actual/heated/effect/rcnld) is unreliable — shows 0
  even for completed buildings. Do not use HTML table for this field.
- AYB / EYB: sourced from remixContext JSON
  path: buildings.units[0].yearBuilt.{actual,effective}
- Zoning: sourced from remixContext JSON, path: zonings[0].code
  Not present in HTML card.
- Sales data: <h6>Sales</h6> section, standard table with interleaved
  Grantor/Grantee rows. Book, Page, Date, Q/U (qualification_code),
  V/I (sale_type), Price columns.
- Sale history captured from same parcelcard page per request.
- parcel_sale_history populated with full ownership chain per parcel.
- instrument_type not surfaced on parcelcard — always None.
- multi_parcel not surfaced on parcelcard — always False.

### Santa Rosa Run Resumability
- cama_enriched_at IS NULL filter skips already-processed parcels automatically.
- Run is fully resumable after any stop (soft-block, empty:true skip, or manual).

### Santa Rosa Data Quality (verified 2026-05-24)
- 7,361 parcels enriched via old parcelview scraper retained — not re-scraped.
- Quality check: 7,330 / 7,361 have tot_lvg_area (99.6%), 7,300 have zoning,
  7,300 have bedrooms, 7,310 have bathrooms. Gaps are genuine vacant/non-standard
  parcels, not scraper failures.

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
- base.py uses settings.host_database_url (async) for DB connection.
  Do not change to settings.database_url — that URL uses the Docker
  service name 'db' and is unreachable from the Windows host.

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
