# Project Penstock - context/cama.md
# Paste this alongside AGENTS.md when working on CAMA ingest.
# Last updated: 2026-06-02

## File Paths

real_invest_fl/ingest/cama/
  base.py           -- shared framework, no county-specific logic
  escambia.py       -- Escambia County scraper
  santa_rosa.py     -- Santa Rosa County scraper
  __init__.py       -- package marker
real_invest_fl/ingest/sales/
  santa_rosa_sales.py   -- Santa Rosa full sale history scraper (item 124)
  __init__.py           -- package marker  
real_invest_fl/ingest/cama_ingest.py  -- retained; do not delete until Escambia confirmed

## Run Commands

# Santa Rosa
python -m real_invest_fl.ingest.cama.santa_rosa [options]

# Santa Rosa full sale history
python -m real_invest_fl.ingest.sales.santa_rosa_sales [options]

# Escambia
python -m real_invest_fl.ingest.cama.escambia [options]
python scripts/run_escambia_cama.py
# Always verify with --limit 5 --dry-run before any live run.

## Escambia CAMA Detail

- Source: https://www.escpa.org/CAMA/Detail_a.aspx?s={parcel_id}
- Site was DOWN 2026-05-04 through approximately 2026-05-24. Restarted 2026-05-26.
- Target: dor_uc = '001', ~106,372 parcels
- Status: IN PROGRESS. ~27,284 / 106,372 SFR parcels enriched as of
  2026-05-29. Soft-block rate limiting active. Resumable via
  cama_enriched_at IS NULL.
- Beds/baths NOT available from ECPA CAMA detail page
- Sale history IS available and captured from ECPA CAMA detail page. 
  parse_sales() reads the Sales Data table (ctl00_MasterPlaceHolder_SalesCell).
  Grantor/grantee not available - stored as empty string.
- Parcel ID format: 16-character no-hyphen string (e.g. 182S303000004001)
  confirmed from DB. URL format matches directly - no transformation needed.
- Run via scripts/run_escambia_cama.py for unattended operation - auto-restarts after soft block with 420s wait.
- Rate limits: DEFAULT_DELAY=2.0, DEFAULT_DELAY_MAX=5.0, REST_EVERY=None, REST_SECONDS=0.0
- Search.aspx redirect = parcel absent from ECPA CAMA - logged as warning,
  cama_enriched_at stamped (excludes from future runs), inter-request delay
  applied, continues run. Returns base.NOT_FOUND sentinel.
- Sale date parsing: MM/DD/YYYY stored as-is. MM/YYYY normalized to
  date(YYYY, MM, 1) and stored. Unparseable formats logged at DEBUG and skipped.
- eff_yr_blt: captured from "Effective Year" label in building table header.

## Santa Rosa CAMA Detail

- Source: https://parcelcard.srcpa.gov/?parcel={parcel_id}&baseUrl=http://srcpa.gov/
- Previous source (parcelview.srcpa.gov) was replaced - site rebuilt as
  Remix/React SSR application. Confirmed 2026-05-24.
- Server-rendered HTML. No JavaScript, auth, or cookies required.
  Plain httpx GET is sufficient.
- No robots.txt on srcpa.gov or parcelcard.srcpa.gov.
- TARGET: dor_uc = '001', 68,312 parcels
- Status: COMPLETE. 68,303 parcels enriched. Second pass complete (2,265
  retry parcels). 9 remaining SFR parcels are edge cases - not a blocker.
  54,453 unenriched parcels are non-SFR dor_uc - will not be scraped.
  No further CAMA runs required until Phase 3 annual refresh pipeline.
- Rate limits: DEFAULT_DELAY=1.0, DEFAULT_DELAY_MAX=3.0,
  REST_EVERY=500, REST_SECONDS=300.0
- Soft-block confirmed at ~2,859 requests over ~1h54m at 1.0–3.0s delay
  with no rest pauses under old endpoint. REST_EVERY=500/REST_SECONDS=300.0
  retained as mitigation.
- SOURCE_NAME: srcpa_parcelcard (updated from srcpa_parcelview)

### Santa Rosa Page Structure (parcelcard.srcpa.gov)
- Valid response: window.__remixContext present in body with full parcel data
- Soft-block signature: window.__remixContext absent entirely - stop run
- Not-found signature: window.__remixContext present, routes/_index loader
  data has "empty":true - skip parcel cleanly, continue run
- Building fields: two-column <td> bold-label/value grid using Tailwind classes.
  Abbreviated labels: extw, RCVR, fndn, Bath, BED, qual
- Heated area (tot_lvg_area): sourced from remixContext JSON
  path: buildings.units[0].squareFeet.heated
  HTML summary table (code/actual/heated/effect/rcnld) is unreliable - shows 0
  even for completed buildings. Do not use HTML table for this field.
- AYB / EYB: sourced from remixContext JSON
  path: buildings.units[0].yearBuilt.{actual,effective}
- Zoning: sourced from remixContext JSON, path: zonings[0].code
  Not present in HTML card.
- Sales data: <h6>Sales</h6> section, standard table with interleaved
  Grantor/Grantee rows. Book, Page, Date, Q/U (qualification_code),
  V/I (sale_type), Price columns.
- Sale history captured from same parcelcard page per request.
- parcel_sale_history populated with up to 2 sales per parcel.
  Parcelcard truncates older records - "... N more" is not scraped.
  Full history source is parcelview.srcpa.gov - see item 124.
- instrument_type not surfaced on parcelcard - always None.
  instrument_type IS available on parcelview.srcpa.gov (full parcel page).
  santa_rosa_sales.py (item 124) captures it from that endpoint.
- multi_parcel not surfaced on parcelcard - always False.

Note: parse_sales() removed from santa_rosa.py (item 127).
santa_rosa_sales.py is the permanent sale history source, quarterly cadence.

### Santa Rosa Run Resumability
- cama_enriched_at IS NULL filter skips already-processed parcels automatically.
- Run is fully resumable after any stop (soft-block, empty:true skip, or manual).
- Run complete as of 2026-05-29. Resumability applies to future refresh runs.

### Santa Rosa Data Quality (verified 2026-05-29)
- 68,303 parcels enriched. Second pass complete.
- tot_lvg_area corrected for 67,543 parcels - NAL re-ingest had
  overwritten CAMA heated area with NAL effective area. Restored from
  raw_cama_json. tot_lvg_area now protected by _NAL_UPSERT_NEVER_OVERWRITE.
- 9 remaining unenriched SFR parcels are edge cases - not a blocker.
- 54,453 unenriched parcels are non-SFR dor_uc - correct by design.

### Santa Rosa Sale History Scraper (santa_rosa_sales.py)
- Source: https://parcelview.srcpa.gov/?parcel={parcel_id}&baseUrl=http://srcpa.gov/
- srcpa.gov/parcel is a wrapper shell - actual data loads via iframe
  pointing to parcelview.srcpa.gov. Scraper targets parcelview directly.
- Server-rendered HTML. Plain httpx GET with browser-mimicking headers.
  No JavaScript rendering required.
- Parse target: <div id="salesContainer"> table. Each <td> carries
  data-cell="<column name>" attribute - used as column selector.
  No positional index logic.
- Soft-block detection: id="salesContainer" absent from response body.
- Not-found detection: salesContainer present, zero <td> data rows.
- source tag: srcpa_parcel (distinct from srcpa_parcelcard).
- Upsert: ON CONFLICT updates instrument_type, qualification_code,
  sale_type, sale_price, multi_parcel, price_per_sqft, source when any
  differ. sale_date, grantor, grantee are immutable (unique key fields).
- Does NOT use base.run(). Own lightweight loop with same rate limits
  as parcelcard scraper: DEFAULT_DELAY=1.0, DEFAULT_DELAY_MAX=3.0,
  REST_EVERY=500, REST_SECONDS=300.0.
- Resumability: --resume-from <parcel_id>. Uses >= comparison (inclusive)
  - safe because upsert is idempotent.
- Target: all dor_uc = '001' parcels (68,312). No cama_enriched_at gate.
- Run complete. Verified 2026-06-02. 323,102 records, 68,009 parcels.
  instrument_type 99.1% populated. qualification_code: Q/U/C/V populated.
  srcpa_parcelcard rows (36,133) retained - non-overlapping keys.

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
- Sentinels:
  - base.SOFT_BLOCK = "__SOFT_BLOCK__" - county fetch_page() returns this
    to stop the run cleanly. Increments failed counter. No DB write.
  - base.NOT_FOUND = "__NOT_FOUND__" - county fetch_page() returns this
    when a parcel is permanently absent from the county PA site (e.g.
    Search.aspx redirect on ECPA). Stamps cama_enriched_at so the parcel
    is excluded from all future runs. Respects inter-request delay.
    Increments not_found counter.
  - Returning None indicates a transient failure (timeout, HTTP error,
    retries exhausted). Increments failed counter. No DB write. Parcel
    remains in queue for next run.
- base.py uses settings.host_database_url (async) for DB connection.
  Do not change to settings.database_url - that URL uses the Docker
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
6. Run enrich_missing_spatial_attrs.py --county-fips {fips} --dor-uc 001
7. Verify _MAILING_ADDR_FIELD layout from raw NAL data, add to nal_ingest.py and compute_absentee_owner.py
8. Run compute_absentee_owner.py --county-fips {fips}
9. Run arv_calculator.py --county-fips {fips}

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
