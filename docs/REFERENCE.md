# Project Penstock — REFERENCE.md

Companion to CHECKPOINT.md. Contains locked design decisions, schema
detail, file paths, scraper notes, completed item archives, and
source investigation results. Paste relevant sections into a new chat
session when working in those areas. Do not paste wholesale at session
open — use CHECKPOINT.md for that.

---

## Key Design Decisions (Locked — Never Override)

### Data Architecture
- ARV proxy = `jv` (Just Value from NAL) until multi-year SDF comps available
- Signal model is primary; traditional listing model is a parallel track
- `listing_events` is the unified output table for all signal and listing sources
- SDF deferred; NAV deferred until deal-scoring is approved deliverable

### Database / ORM
- Session pattern: async (`settings.database_url`) for ORM;
  sync (`settings.sync_database_url`) for batch scripts
- All SQL in batch scripts uses `text()` — never raw string SQL
- `CAST(:raw_listing_json AS jsonb)` — never `::jsonb` in `text()` statements

### Parcel ID Normalization
- Strip non-alphanumeric, uppercase, NO zero-padding.
- `properties.parcel_id` stored as 16 chars.
- `normalize_parcel_id()` in `parcel_id.py` zero-pads to 18 — do NOT call
  it in scrapers; it will break the join. Use raw strip+uppercase only.

### Street Address Normalization
- `normalize_street_address()` in `real_invest_fl/utils/text.py` is the
  single shared normalizer for all scrapers and listing_matcher.
- Transformations (in order): upper-case, unit strip, digit-letter injection
  (ordinals excluded), suffix abbreviation, directional contraction.
- Digit-letter injection: `(\d)(?!(?:ST|ND|RD|TH)\b)([A-Z])` — excludes
  ordinal suffixes (74TH, 48TH).
- Unit stripping runs BEFORE digit-letter injection.
- `#` unit designator has no leading `\b` anchor — `#` is not a word char.
- `strip_unit=False` preserves unit designators for Level 2 lookup.
- `listing_matcher._normalize_address()` delegates to `normalize_street_address()`.
- Address matching: three-level fallback — exact match, unit suffix
  normalization (#4A → 4A), street prefix with MULTI-UNIT review flag.
- Library: rapidfuzz v3.14.5
- 50 tests passing as of 2026-04-28.

### Ingest Pipeline
- Filters are query-time only. The ingest pipeline never applies filter
  criteria to determine what gets written to the database. Every parcel
  from every county NAL goes into properties regardless of use code, size,
  value, or any other criterion.
- All ingest scripts resolve file paths programmatically from the county
  registry using the canonical folder pattern:
    data/raw/counties/{fips}_{snake_name}/{type}/
  where snake_name = county_name.lower().replace('-','_').replace(' ','_')
  File discovery uses globs, never hardcoded filenames:
    NAL: next(nal_dir.glob("NAL*.csv"))
    GIS: next(gis_dir.glob("*.shp"))
- CRS detection is per-county at runtime via gdf.crs. COUNTY_REGISTRY
  stores the confirmed CRS per county for documentation and warning
  suppression only. gdf.crs.to_epsg() is authoritative — not the raw
  .prj text. Santa Rosa confirmed EPSG:2883 (not EPSG:2881 as the raw
  .prj text suggested).
- Florida statewide bounding box for centroid sanity checks:
  FL_LAT_MIN/MAX = 24.4/31.1, FL_LON_MIN/MAX = -87.65/-80.0.
  Western boundary is -87.65, not -87.6 — confirmed against 18 valid
  Escambia parcels along the Perdido River.
  
### CAMA Ingest Framework

Subpackage: real_invest_fl/ingest/cama/
  base.py        — shared framework, no county-specific logic
  escambia.py    — Escambia County scraper
  santa_rosa.py  — Santa Rosa County scraper
  __init__.py    — package marker

base.py design rules (never override):
- coerce_building() returns (coerced: dict, null_cols: set[str])
  null_cols contains columns explicitly rejected by sanity guards —
  write_cama() writes NULL for these regardless of existing DB value.
  This is distinct from absent/unparseable fields which return None
  and are silently skipped.
- write_cama() never overwrites a good DB value with None from a
  failed parse, but DOES overwrite with NULL for guard-rejected values.
- All rate-limiting parameters are county-supplied. base.py has no
  defaults. County module must declare: DEFAULT_DELAY, DEFAULT_DELAY_MAX,
  REST_EVERY (None = no rest pauses), REST_SECONDS.
- target_dor_ucs is county-supplied — e.g. ['001'] for single-family.
  Never hardcoded in base.py.
- Soft-block sentinel: base.SOFT_BLOCK = "__SOFT_BLOCK__"
  County fetch_page() returns this to stop the run cleanly.
  Returning None skips the parcel and continues the run.

parcel_sale_history table:
  Stores full ownership chain per parcel from county PA scrape.
  Distinct from sales_comps (SDF-sourced qualified arm's-length only).
  Unique constraint: uq_psh_county_parcel_sale on
  (county_fips, parcel_id, sale_date, grantor, grantee).
  grantor/grantee NOT NULL DEFAULT '' — empty string used in place of
  NULL to ensure unique constraint fires correctly.

dor_uc normalization:
  Florida DOR specifies use codes as three-digit zero-padded strings.
  Some county NAL files ship unpadded (Escambia: '1', '2', '93').
  nal_mapper.py _dor_uc() helper normalizes all variants to '001',
  '002', '093' etc. at ingest time.
  Escambia rows backfilled via:
    UPDATE properties SET dor_uc = LPAD(TRIM(dor_uc), 3, '0')
    WHERE county_fips = '12033' AND dor_uc IS NOT NULL
    AND LENGTH(TRIM(dor_uc)) < 3;

Santa Rosa parcelview notes:
  URL: https://parcelview.srcpa.gov/?parcel={parcel_id}&baseUrl=http://srcpa.gov/
  Server-rendered HTML, no JS/auth/cookies required.
  Valid page marker: 'residentialBuildingsContainer'
  Soft-block response: HTTP 200 with disclaimer-only body.
  No robots.txt on srcpa.gov or parcelview.srcpa.gov.
  Soft-block confirmed at ~2,859 requests over ~1h54m with no rest pauses.
  Current rate limit settings: 1.0-3.0s delay, REST_EVERY=500,
  REST_SECONDS=300.0.
  Building data parsed from data-cell attribute pattern — no regex,
  no sibling traversal. Sales data from salesContainer div, same pattern.
  Zoning from zoningContainer div, Code cell.

### Scraping / Robots
- Tier 1 government sources (RealForeclose, RealTaxDeed, LandmarkWeb):
  file-drop parsers — robots.txt blocks live scraping on all three.
- `public.escambiaclerk.com`: generic crawlers permitted; ClaudeBot blocked
  by name. Behind Cloudflare — Playwright required, requests blocked.
- Scraper auto-discovery via `real_invest_fl/scrapers/` package imports.

### Beds / Baths
- Populated opportunistically on parcel match from any listing source.
- `bed_bath_source` tracks provenance.
- Never overwrite an existing value with a lower-confidence source —
  logic lives in the parser layer.

### Signal Tiers
- Signal tier reflects delivery source, not underlying event type.
- A foreclosure on Zillow is Tier 3; same event from Escambia Clerk is Tier 1.

### Workflow Patterns
- Zillow workflow: --dry-run first to surface [REVIEW] items, then live run.
  Standard for all attended file-drop parsers.
- Long-running processes in dedicated PowerShell windows are approved pattern.
- Machine runs 24/7.

### Windows / Python Platform Notes
- Windows / Python 3.13 strptime: use `%b` (abbreviated) not `%B` (full).
  Escambia Clerk pages deliver abbreviated month names. `%B` fails silently.

### Subscription and Access Model (Locked)
- County is the fundamental unit of access control and monetization.
- Subscription tiers: single county, regional bundle, statewide, enterprise.
- First bundle: Pensacola Metro = Escambia (12033) + Santa Rosa (12113).
- First expansion county: Santa Rosa (FIPS 12113).
- User-county authorization: `user_county_access` join table.
- County access enforced via single reusable FastAPI dependency — not at
  the application layer.
- Multi-user from day one. No single-admin stub acceptable.

### Filter Profile Model (Locked)
- Profiles scoped to county_fips.
- System profiles: user_id = NULL, visible to all authorized users,
  not editable or deletable by users.
- Users clone a system profile to create a private editable copy —
  "Save as my profile" is a first-class UI action.
- User profiles: user_id = owner, private, fully editable.
- Uniqueness enforced via two partial unique indexes (live in DB, v0.13):
  - System: UNIQUE (county_fips, profile_name) WHERE user_id IS NULL
  - User: UNIQUE (user_id, county_fips, profile_name) WHERE user_id IS NOT NULL
- Cross-county profiles deferred to Phase 3+.

### Scoring and Filter Enforcement Model (Locked)
- Filters are query-time only. The ingest pipeline never applies filter
  criteria to determine what gets written to the database. Every parcel
  from every county NAL is written as-is regardless of use code, size,
  value, or any other criterion.
- passed_filters, filter_rejection_reasons, deal_score are computed at
  query time against the standing inventory — not at ingest time.
- deal_score_version tracks algorithm version for auditability.
- Filter profile save/modify triggers background recompute of
  listing_events for that county_fips — Phase 4 dependency.
- API routes sort and filter on pre-computed columns only.
- mqi_qualified, mqi_rejection_reasons, mqi_qualified_at are POC
  artifacts. All rows carry mqi_qualified = false as a neutral
  placeholder. These columns will be removed in a future migration
  once the query-time filter (Phase 4) is live.

### Auth Model (Locked — Item 5)
- JWT HS256 via PyJWT. sub = users.id as string. email included as
  display hint only — never used for identity lookup.
- Token payload: sub, email, type="access", iat, exp.
- Password hashing: bcrypt direct (passlib dropped — incompatible with
  bcrypt 4.0+).
- get_current_user: decodes JWT, extracts user id, loads User from DB,
  raises 401 on failure or inactive user.
- require_county_access: superuser bypass, otherwise checks
  user_county_access for (user_id, county_fips) row, raises 403 on denial.
- Auth routes: POST /auth/token, GET /auth/me only.
  Registration, password reset, user management deferred to Phase 4.
- Operational follow-ups before Phase 4:
  - Run seed_superuser.py to create first superuser
  - Run seed_bundles.py to seed Pensacola Metro, activate Santa Rosa
  - Standardize require_county_access path-parameter pattern before
    Phase 4 endpoints proliferate

---

## ROOT Path Bootstrap Rules

ROOT must resolve to: `D:\Chris\Documents\Stratyne\real_invest_fl\`

| File location | ROOT expression |
|---|---|
| `scripts/*.py` | `Path(__file__).resolve().parent.parent` |
| `real_invest_fl/ingest/*.py` | `Path(__file__).resolve().parent.parent.parent` |
| `real_invest_fl/scrapers/*.py` | `Path(__file__).resolve().parent.parent.parent` |
| `real_invest_fl/ingest/staging_parsers/*.py` | `Path(__file__).resolve().parent.parent.parent.parent` |

Standard bootstrap block:

python
ROOT = Path(__file__).resolve().parent.parent.parent  # adjust per table
sys.path.insert(0, str(ROOT))
from config.settings import settings
from sqlalchemy import create_engine, text
engine = create_engine(settings.sync_database_url)


---

## Relevant File Paths


real_invest_fl/                          <- project root
├── alembic/versions/                    <- all migration files
├── config/
│   ├── settings.py                      <- Pydantic BaseSettings
│   └── filter_profiles/
│       └── escambia_poc.json
├── data/
│   ├── raw/                             <- NAL CSV, SDF CSV, GIS zips
│   └── staging/
│       ├── lis_pendens/
│       ├── foreclosure/
│       ├── tax_deed/
│       └── zillow/
├── real_invest_fl/
│   ├── api/
│   │   ├── main.py                      <- FastAPI app, auth router wired
│   │   ├── deps.py                      <- get_db, get_current_user,
│   │   │                                   require_county_access
│   │   └── routes/
│   │       ├── auth.py                  <- POST /auth/token, GET /auth/me
│   │       ├── approvals.py             <- stub
│   │       ├── config.py                <- stub
│   │       ├── counties.py              <- stub
│   │       ├── dashboard.py             <- stub
│   │       ├── ingest.py                <- stub
│   │       ├── listings.py              <- stub
│   │       ├── outreach.py              <- stub
│   │       └── properties.py            <- stub
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── passwords.py                 <- hash_password, verify_password
│   │   └── tokens.py                    <- create_access_token,
│   │                                       decode_access_token,
│   │                                       extract_user_id
│   ├── db/
│   │   ├── base.py
│   │   ├── session.py                   <- async session, get_db
│   │   └── models/
│   │       ├── __init__.py
│   │       ├── county.py
│   │       ├── user.py                  <- NEW v0.13
│   │       ├── user_county_access.py    <- NEW v0.13
│   │       ├── subscription_bundle.py   <- NEW v0.13
│   │       ├── filter_profile.py        <- user_id added v0.13
│   │       ├── outreach_log.py          <- user_id added v0.13
│   │       ├── property.py
│   │       ├── listing_event.py
│   │       ├── ingest_run.py
│   │       ├── data_source_status.py
│   │       ├── email_template.py
│   │       ├── permit_record.py
│   │       ├── property_history.py
│   │       ├── public_record.py
│   │       ├── sales_comp.py
│   │       └── zestimate_cache.py
│   ├── ingest/
│   │   ├── arv_calculator.py
│   │   ├── cama_ingest.py
│   │   ├── gis_ingest.py
│   │   ├── listing_matcher.py           <- centralized parcel lookup
│   │   ├── nal_filter.py
│   │   ├── nal_ingest.py
│   │   ├── nal_mapper.py
│   │   ├── run_auction_com.py           <- COMPLETE
│   │   ├── run_context.py
│   │   ├── run_taxdeed.py               <- COMPLETE
│   │   ├── source_status.py             <- data_source_status upsert helper
│   │   └── staging_parsers/
│   │       ├── __init__.py
│   │       ├── foreclosure_parser.py
│   │       ├── lis_pendens_parser.py
│   │       ├── tax_deed_parser.py
│   │       └── zillow_parser.py         <- COMPLETE
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── auction_com.py               <- COMPLETE
│   │   ├── base_scraper.py
│   │   ├── escambia_foreclosure.py      <- robots-blocked, retained
│   │   └── escambia_taxdeed_clerk.py    <- COMPLETE
│   └── utils/
│       ├── parcel_id.py
│       ├── robots.py
│       └── text.py                      <- normalize_street_address()
└── scripts/
    ├── cold_start.py
    ├── probe_auction_com.py             <- investigation only
    ├── probe_auction_com_request.py     <- investigation only
    ├── run_arv.py
    ├── run_staging_import.py
    └── seeds/
        ├── seed_counties.py
        ├── seed_county_zips.py
        ├── seed_filter_profile.py
        ├── seed_bundles.py              <- NEW v0.13
        └── seed_superuser.py            <- NEW v0.13


---

## Schema Reference

          Column           |           Type           | Collation | Nullable | Default
---------------------------+--------------------------+-----------+----------+---------
 county_fips               | character varying(5)     |           | not null |
 parcel_id                 | character varying(30)    |           | not null |
 state_par_id              | character varying(30)    |           | not null |
 co_no                     | integer                  |           |          |
 asmnt_yr                  | integer                  |           |          |
 dor_uc                    | character varying(10)    |           |          |
 pa_uc                     | character varying(10)    |           |          |
 jv                        | integer                  |           |          |
 av_nsd                    | integer                  |           |          |
 tv_nsd                    | integer                  |           |          |
 const_class               | integer                  |           |          |
 eff_yr_blt                | integer                  |           |          |
 act_yr_blt                | integer                  |           |          |
 tot_lvg_area              | integer                  |           |          |
 lnd_sqfoot                | integer                  |           |          |
 no_buldng                 | integer                  |           |          |
 no_res_unts               | integer                  |           |          |
 own_name                  | character varying(200)   |           |          |
 own_addr1                 | character varying(200)   |           |          |
 own_addr2                 | character varying(200)   |           |          |
 own_city                  | character varying(100)   |           |          |
 own_state                 | character varying(25)    |           |          |
 own_zipcd                 | character varying(10)    |           |          |
 phy_addr1                 | character varying(300)   |           |          |
 phy_city                  | character varying(100)   |           |          |
 phy_zipcd                 | character varying(10)    |           |          |
 absentee_owner            | boolean                  |           |          |
 foundation_type           | character varying(100)   |           |          |
 exterior_wall             | character varying(100)   |           |          |
 roof_type                 | character varying(100)   |           |          |
 bedrooms                  | integer                  |           |          |
 bathrooms                 | numeric(4,1)             |           |          |
 cama_quality_code         | character varying(10)    |           |          |
 cama_condition_code       | character varying(10)    |           |          |
 cama_enriched_at          | timestamp with time zone |           |          |
 geom                      | geometry(Point,4326)     |           |          |
 latitude                  | numeric(10,7)            |           |          |
 longitude                 | numeric(10,7)            |           |          |
 mqi_qualified             | boolean                  |           | not null |
 mqi_qualified_at          | timestamp with time zone |           |          |
 mqi_rejection_reasons     | jsonb                    |           |          |
 mqi_stage                 | character varying(10)    |           |          |
 seller_probability_score  | numeric(5,4)             |           |          |
 seller_score_updated_at   | timestamp with time zone |           |          |
 permit_count              | integer                  |           |          |
 estimated_rehab_per_sqft  | numeric(6,2)             |           |          |
 raw_nal_json              | jsonb                    |           |          |
 raw_cama_json             | jsonb                    |           |          |
 nal_ingested_at           | timestamp with time zone |           |          |
 created_at                | timestamp with time zone |           | not null | now()
 updated_at                | timestamp with time zone |           | not null | now()
 imp_qual                  | integer                  |           |          |
 spec_feat_val             | integer                  |           |          |
 av_sd                     | integer                  |           |          |
 tv_sd                     | integer                  |           |          |
 jv_hmstd                  | integer                  |           |          |
 lnd_val                   | integer                  |           |          |
 exmpt_01                  | integer                  |           |          |
 multi_par_sal1            | character varying(1)     |           |          |
 qual_cd1                  | character varying(2)     |           |          |
 vi_cd1                    | character varying(1)     |           |          |
 sale_prc1                 | integer                  |           |          |
 sale_yr1                  | integer                  |           |          |
 sale_mo1                  | integer                  |           |          |
 sal_chng_cd1              | character varying(1)     |           |          |
 multi_par_sal2            | character varying(1)     |           |          |
 qual_cd2                  | character varying(2)     |           |          |
 vi_cd2                    | character varying(1)     |           |          |
 sale_prc2                 | integer                  |           |          |
 sale_yr2                  | integer                  |           |          |
 sale_mo2                  | integer                  |           |          |
 sal_chng_cd2              | character varying(1)     |           |          |
 own_state_dom             | character varying(2)     |           |          |
 distr_cd                  | integer                  |           |          |
 distr_yr                  | integer                  |           |          |
 nconst_val                | integer                  |           |          |
 del_val                   | integer                  |           |          |
 par_splt                  | character varying(5)     |           |          |
 spass_cd                  | character varying(1)     |           |          |
 mkt_ar                    | character varying(3)     |           |          |
 nbrhd_cd                  | character varying(10)    |           |          |
 census_bk                 | character varying(16)    |           |          |
 twn                       | character varying(3)     |           |          |
 rng                       | character varying(3)     |           |          |
 sec                       | character varying(3)     |           |          |
 dt_last_inspt             | character varying(4)     |           |          |
 alt_key                   | character varying(26)    |           |          |
 s_legal                   | character varying(30)    |           |          |
 improvement_to_land_ratio | numeric(8,4)             |           |          |
 soh_compression_ratio     | numeric(6,4)             |           |          |
 years_since_last_sale     | integer                  |           |          |
 zoning                    | character varying(20)    |           |          |
 nav_total_assessment      | numeric(12,2)            |           |          |
 jv_per_sqft               | numeric                  |           |          |
 arv_estimate              | integer                  |           |          |
 arv_spread                | integer                  |           |          |
 list_price                | integer                  |           |          |
 bed_bath_source           | character varying(50)    |           |          |
Indexes:
    "uq_county_parcel" PRIMARY KEY, btree (county_fips, parcel_id)
    "idx_properties_geom" gist (geom)
    "ix_properties_act_yr_blt" btree (act_yr_blt)
    "ix_properties_alt_key" btree (alt_key)
    "ix_properties_census_bk" btree (census_bk)
    "ix_properties_const_class" btree (const_class)
    "ix_properties_county_fips" btree (county_fips)
    "ix_properties_dor_uc" btree (dor_uc)
    "ix_properties_jv" btree (jv)
    "ix_properties_mkt_ar" btree (mkt_ar)
    "ix_properties_mqi_qualified" btree (mqi_qualified)
    "ix_properties_phy_zipcd" btree (phy_zipcd)
    "ix_properties_sale_yr1" btree (sale_yr1)
    "ix_properties_state_par_id" btree (state_par_id)

### listing_events (confirmed 2026-04-27)

id                       INTEGER PK
county_fips              VARCHAR(5)   NOT NULL
parcel_id                VARCHAR(30)  NOT NULL
listing_type             VARCHAR(50)
list_price               INTEGER
list_date                DATE
expiry_date              DATE
days_on_market           INTEGER
source                   VARCHAR(100)
listing_url              VARCHAR(1000)
listing_agent_name       VARCHAR(200)
listing_agent_email      VARCHAR(200)
listing_agent_phone      VARCHAR(30)
mls_number               VARCHAR(50)  — no unique constraint
price_per_sqft           NUMERIC(8,2)
arv_estimate             INTEGER
arv_source               VARCHAR(20)
rehab_cost_estimate      INTEGER
arv_spread               INTEGER
zestimate_value          INTEGER
zestimate_discount_pct   NUMERIC(6,3)
zestimate_fetched_at     TIMESTAMPTZ
deal_score               NUMERIC(5,4)
deal_score_version       VARCHAR(20)
deal_score_components    JSONB
filter_profile_id        INTEGER
passed_filters           BOOLEAN
filter_rejection_reasons JSONB
workflow_status          VARCHAR(30)  NOT NULL
notes                    TEXT
raw_listing_json         JSONB
scraped_at               TIMESTAMPTZ
created_at               TIMESTAMPTZ  NOT NULL default now()
updated_at               TIMESTAMPTZ  NOT NULL default now()
signal_tier              INTEGER
signal_type              VARCHAR(50)
Indexes: listing_events_pkey, ix_le_county_parcel, ix_le_deal_score,
         ix_le_listing_type, ix_le_status, ix_le_signal_tier,
         ix_le_signal_type

### properties CAMA columns (confirmed 2026-04-28)

foundation_type      VARCHAR(100)  nullable
exterior_wall        VARCHAR(100)  nullable
roof_type            VARCHAR(100)  nullable
bedrooms             INTEGER       nullable
bathrooms            NUMERIC(4,1)  nullable
bed_bath_source      VARCHAR(50)   nullable
cama_quality_code    VARCHAR(10)   nullable
cama_condition_code  VARCHAR(10)   nullable
cama_enriched_at     TIMESTAMPTZ   nullable

### users (v0.13)

id               INTEGER PK autoincrement
email            VARCHAR(255) NOT NULL UNIQUE
hashed_password  VARCHAR(255) NOT NULL
full_name        VARCHAR(200) nullable
is_active        BOOLEAN NOT NULL default true
is_superuser     BOOLEAN NOT NULL default false
created_at       TIMESTAMPTZ NOT NULL default now()
updated_at       TIMESTAMPTZ NOT NULL default now()

### user_county_access (v0.13)

id                  INTEGER PK autoincrement
user_id             INTEGER NOT NULL FK → users.id ON DELETE CASCADE
county_fips         VARCHAR(5) NOT NULL FK → counties.county_fips
granted_at          TIMESTAMPTZ NOT NULL default now()
granted_by_user_id  INTEGER nullable FK → users.id ON DELETE SET NULL
UNIQUE (user_id, county_fips)

### subscription_bundles (v0.13)

id           INTEGER PK autoincrement
bundle_name  VARCHAR(100) NOT NULL UNIQUE
description  VARCHAR(500) nullable
is_active    BOOLEAN NOT NULL default true
created_at   TIMESTAMPTZ NOT NULL default now()

### bundle_counties (v0.13)

bundle_id    INTEGER NOT NULL FK → subscription_bundles.id ON DELETE CASCADE
county_fips  VARCHAR(5) NOT NULL FK → counties.county_fips
PRIMARY KEY (bundle_id, county_fips)

---

## Staging File-Drop Workflow

| Source | Staging folder | Format | Cadence |
|---|---|---|---|
| LandmarkWeb lis pendens | data/staging/lis_pendens/ | .xlsx | Weekly |
| RealForeclose foreclosures | data/staging/foreclosure/ | .csv (2-col key-value) | Weekly |
| Zillow listings | data/staging/zillow/ | .csv (one value per line) | Weekly |

python scripts/run_staging_import.py --source lis_pendens
python scripts/run_staging_import.py --source foreclosure
python scripts/run_staging_import.py --source zillow

Tax deed data is sourced via direct scraper, not file-drop.
`data/staging/tax_deed/` retained pending Ch. 119 response.

---

## Escambia Clerk Tax Deed — Direct Scrape (COMPLETE)

- Scraper: `real_invest_fl/scrapers/escambia_taxdeed_clerk.py`
- Runner: `real_invest_fl/ingest/run_taxdeed.py`
- Date list: https://public.escambiaclerk.com/taxsale/taxsaledates.asp
- Per-date: https://public.escambiaclerk.com/taxsale/taxsaleMobile.asp?saledate=M/D/YYYY
- saledate format: M/D/YYYY, no zero-padding, no percent-encoding —
  build URL as string, never use requests params dict
- Table: `soup.find("table", attrs={"bgcolor": "#0054A6"})`
- Columns: Clerk File #, Account, Certificate Number, Reference (parcel ID),
  Sales Date, Status, Opening Bid Amount, Legal Description,
  Surplus Balance, Property Address
- Dedup key: `listing_events.mls_number = Clerk File #`
- signal_tier=1, signal_type='tax_deed', source='escambia_clerk_taxsale'
- Historical backfill complete: 5,730 records, 2019-01-07 – 2026-12-02

python real_invest_fl/ingest/run_taxdeed.py --upcoming
python real_invest_fl/ingest/run_taxdeed.py --historical
python real_invest_fl/ingest/run_taxdeed.py --date 5/6/2026

---

## Scraper Source Tiers

| Tier | Sources | Approach | Status |
|---|---|---|---|
| 1 — Government direct | Escambia Clerk tax deed, lis pendens, foreclosures, RealTaxDeed | Live scrape or file-drop | Tax deed complete; others file-drop |
| 2 — Public aggregators | HUD Home Store, Foreclosure.com | Playwright + rate limiting | Auction.com COMPLETE; others pending |
| 3 — Free listing sources | Craigslist FSBO | requests + BS4 | Deferred indefinitely |
| 4 — Commercial platforms | Zillow, Redfin, Realtor.com, Homes.com | Paid API or vendor proxy | Deferred |

---

## Per-Scraper Implementation Notes

### auction_com.py
- `_normalize_street()` is intentionally minimal — digit-letter injection
  and upper/collapse only. Do not expand.
- GraphQL API: POST https://graph.auction.com/graphql
- No auth required. x-cid header must be fresh UUID per request.
- Remove $hasAuthenticatedUser from operation signature AND variables.
- Returns 50-mile radius (~73 records). Filter:
  country_primary_subdivision=FL AND country_secondary_subdivision=ESCAMBIA
  (case-insensitive). 14-17 records survive.
- total_bedrooms=0 and total_bathrooms=0 are missing-data sentinels → None.
- Wired through listing_matcher.py lookup_parcel_by_address().
- Not yet wired through BaseScraper discovery.
- Unmatched: 2983 NORTH HIGHWAY 95 A → 2983 N HWY 95 A.
  Suspected NAL storage format mismatch, not a normalization defect.

### escambia_taxdeed_clerk.py
- Table nested inside wrapper — use bgcolor="#0054A6" selector always.
- Windows Python 3.13: use %b not %B for month parsing.

### zillow_parser.py (staging)
- Accepts mixed listing types. listing_type and signal_type derived from
  specs line suffix, not hardcoded.
- _extract_street() uses strip_unit=False.
- _normalize_address() uses strip_unit=True (dedup key only).
- _extract_zip() anchors to end of string (\b(\d{5})\s*$).
- Wired through listing_matcher.py lookup_parcel_by_address().

---

## Source Investigation Results (Manual, 2026-04-28)

### Tier 1 — Tax Delinquency
- Escambia Tax Collector delinquent page: navigation hub only, no data.
- escambia.county-taxes.com: landing page only, dead end.
- LienHub advertised list: high-value bulk list, available after May 5 2026.
  URL: https://lienhub.com/county/escambia/certsale/main?unique_id=41C54840429511F1A2F69948A6B8334F&use_this=print_advertised_list
- LienExpress: redirect to LienHub, not a standalone source.

### Tier 2 — Government Auction
- Escambia County Surplus Auctions: zero listings at investigation date.
  Monitor periodically. https://myescambia.com/our-services/property-sales/surplus-property-auction
- HUD Home Store: zero Escambia listings at investigation date. Monitor.
  https://www.hudhomestore.gov/searchresult?citystate=FL
- Auction.com: COMPLETE. 17 listings at investigation date.

### Tier 3 — Commercial / FSBO
- Craigslist: feasible technically, messy data, deferred indefinitely.
- Zillow: good data quality, anti-scraping posture is obstacle.
  RapidAPI wrapper is approved POC approach. Deferred to Tier 4.
- Facebook Marketplace: login required, TOS risk, manual-only.

---

## Completed Item Archive

### Item 2 — Address Normalization (COMPLETE)
`normalize_street_address()` in `real_invest_fl/utils/text.py`.
strip_unit=False parameter added 2026-04-28. Bug fixed 2026-05-01:
digit-letter injection confined to pre-unit portion when strip_unit=False.
50 tests passing. 2 additional tests in test_listing_matcher_lookup.py.

### Item 3 — listing_matcher.py Architectural Resolution (COMPLETE)
auction_com.py and zillow_parser.py route through
lookup_parcel_by_address() in listing_matcher.py. Per-scraper
_lookup_parcel() and bed/bath enrichment duplicates retired.
Follow-ups: 2983 N HWY 95 A still unmatched; auction_com.py not yet
wired through BaseScraper; parser-layer bed/bath confidence hierarchy
deferred.

### Item 4 — data_source_status Table (COMPLETE)
Migration e5f6a7b8c9d0 (v0.12). Composite PK (source, county_fips).
Shared upsert helper in source_status.py. Integrated in run_taxdeed.py,
run_auction_com.py, run_staging_import.py. Sources supported:
escambia_clerk_taxsale, auction_com, zillow_foreclosure,
escambia_landmarkweb, escambia_realforeclose, escambia_realtaxdeed.

### Item 5 — User/Tenant Model and Auth Infrastructure (COMPLETE)
Migration f7a8b9c0d1e2 (v0.13). Tables: users, user_county_access,
subscription_bundles, bundle_counties. filter_profiles.user_id added.
outreach_log.user_id added. ui_sessions dropped. JWT HS256 via PyJWT,
bcrypt direct. Auth routes: POST /auth/token, GET /auth/me.
Dependencies: get_current_user, require_county_access (superuser bypass).
Seed scripts: seed_bundles.py, seed_superuser.py.
115 tests passing. Two-pass code review completed and approved.
passlib dropped — incompatible with bcrypt 4.0+/5.0.0.

### Item 33 — parcel_sale_history Table (COMPLETE)
Migrations g8h9i0j1k2l3 (v0.14) and h9i0j1k2l3m4 (v0.15).
Stores full ownership chain per parcel from county PA scrape.
Distinct from sales_comps (SDF-sourced qualified arm's-length only).
Unique constraint uq_psh_county_parcel_sale on
(county_fips, parcel_id, sale_date, grantor, grantee).
grantor/grantee NOT NULL DEFAULT '' — empty string used in place of
NULL to ensure unique constraint fires correctly.
17,596+ rows as of 2026-05-04, Santa Rosa only.

### Item 34 — Multi-County CAMA Framework (COMPLETE)
Subpackage: real_invest_fl/ingest/cama/
  base.py, escambia.py, santa_rosa.py, __init__.py
All rate-limiting parameters county-supplied. No shared defaults.
coerce_building() returns (coerced, null_cols) tuple.
write_cama() explicitly NULLs guard-rejected fields.
cama_ingest.py retained — do not delete until Escambia testing confirmed.
Santa Rosa CAMA ingest in progress: 3,518/68,312 enriched as of 2026-05-04.
See CAMA Status section in CHECKPOINT for full operational detail.
