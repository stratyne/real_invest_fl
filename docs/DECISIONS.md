# Project Penstock — DECISIONS.md
# Locked architectural decisions and schema reference.
# Append-only — never edit a decision, supersede it with a dated entry.
# Last updated: 2026-05-04

---

## Strategic Vision

Penstock is a multi-user, inventory-first real estate investment property
discovery and scoring platform for Florida. It ingests the complete public
property tax roll for every Florida county — every parcel, every use code,
no filtering at ingest time — and stores it as a clean, queryable inventory.
Users build and manage their own filter models that run against that shared
inventory at query time.

Long-term: statewide platform covering all 67 FL counties, competing
commercially with PropStream. Escambia County is the proof-of-concept.

The original SOW (single investor, single county, hardcoded criteria,
Google Sheet output) is ONE example of what a single user's filter profile
produces. It is not the architecture. It is a test case.

---

## Data Architecture

- ARV proxy = `jv` (Just Value from NAL) until multi-year SDF comps available.
- Signal model is primary; traditional listing model is a parallel track.
- `listing_events` is the unified output table for all signal and listing sources.
- SDF deferred. NAV deferred until deal-scoring is approved deliverable.
- The platform serves infinite users with infinite use cases.

---

## Ingest Pipeline

- Filters are query-time only. The ingest pipeline NEVER applies filter criteria.
  Every parcel from every county NAL goes into properties regardless of use code,
  size, value, or any other criterion.
- All ingest scripts resolve file paths programmatically from the county registry
  using the canonical folder pattern:
    `data/raw/counties/{fips}_{snake_name}/{type}/`
  where snake_name = county_name.lower().replace('-','_').replace(' ','_')
- File discovery uses globs, never hardcoded filenames:
    NAL: `next(nal_dir.glob("NAL*.csv"))`
    GIS: `next(gis_dir.glob("*.shp"))`
- CRS detection is per-county at runtime via `gdf.crs`. COUNTY_REGISTRY stores
  confirmed CRS for documentation only. `gdf.crs.to_epsg()` is authoritative.
- Florida statewide bounding box for centroid sanity checks:
  FL_LAT_MIN/MAX = 24.4/31.1, FL_LON_MIN/MAX = -87.65/-80.0
  Western boundary is -87.65 (confirmed against 18 Escambia parcels on Perdido River).
- dor_uc normalized to zero-padded three digits ('001', '002', '093') at ingest
  via nal_mapper.py `_dor_uc()` helper.
- mqi_qualified, mqi_rejection_reasons, mqi_qualified_at are POC artifacts.
  All rows carry mqi_qualified = false as neutral placeholder. These columns
  will be removed in a future migration once Phase 4 query-time filter is live.

---

## Database / ORM

- Session pattern:
  - Async (`settings.database_url`): ORM / FastAPI routes
  - Sync (`settings.sync_database_url`): batch scripts, seed scripts, ingest
- All SQL in batch scripts uses `text()` — never raw string SQL.
- `CAST(:raw_listing_json AS jsonb)` — never `::jsonb` in `text()` statements.

---

## Parcel ID Normalization

- Strip non-alphanumeric, uppercase, NO zero-padding.
- `properties.parcel_id` stored as 16 chars.
- `normalize_parcel_id()` in `parcel_id.py` zero-pads to 18 — do NOT call it
  in scrapers. Use raw strip+uppercase only in all scraper code.

---

## Street Address Normalization

- `normalize_street_address()` in `real_invest_fl/utils/text.py` is the single
  shared normalizer for all scrapers and listing_matcher.
- Transformations (in order): upper-case → unit strip → digit-letter injection
  (ordinals excluded) → suffix abbreviation → directional contraction.
- Digit-letter injection regex: `(\d)(?!(?:ST|ND|RD|TH)\b)([A-Z])` — excludes
  ordinal suffixes (74TH, 48TH).
- Unit stripping runs BEFORE digit-letter injection.
- `#` unit designator has no leading `\b` anchor — `#` is not a word char.
- `strip_unit=False` preserves unit designators for Level 2 lookup.
- `listing_matcher._normalize_address()` delegates to `normalize_street_address()`.
- Address matching: three-level fallback — exact match → unit suffix
  normalization (#4A → 4A) → street prefix with MULTI-UNIT review flag.
- Library: rapidfuzz v3.14.5
- 50 tests passing as of 2026-04-28.

---

## CAMA Ingest Framework

- Subpackage: `real_invest_fl/ingest/cama/`
  - `base.py` — shared framework, no county-specific logic
  - `escambia.py` — Escambia County scraper
  - `santa_rosa.py` — Santa Rosa County scraper
  - `__init__.py` — package marker
- `coerce_building()` returns `(coerced: dict, null_cols: set[str])`.
  `null_cols` = columns explicitly rejected by sanity guards.
  `write_cama()` writes NULL for these regardless of existing DB value.
  Absent/unparseable fields return None and are silently skipped.
- `write_cama()` never overwrites a good DB value with None, but DOES
  overwrite with NULL for guard-rejected values.
- All rate-limiting parameters are county-supplied. `base.py` has NO defaults.
  County module must declare: DEFAULT_DELAY, DEFAULT_DELAY_MAX,
  REST_EVERY (None = no rest pauses), REST_SECONDS.
- `target_dor_ucs` is county-supplied. Never hardcoded in base.py.
- Soft-block sentinel: `base.SOFT_BLOCK = "__SOFT_BLOCK__"`
  County `fetch_page()` returns this to stop the run cleanly.
  Returning None skips the parcel and continues the run.
- Each county property appraiser has a different website, URL pattern,
  and HTML structure. No shared scraper is possible.
- New county checklist:
  1. Check robots.txt at county PA domain
  2. Inspect parcel page HTML structure
  3. Determine rate limit empirically (start conservative)
  4. Create `real_invest_fl/ingest/cama/{county_snake}.py`
  5. Add to COUNTY_REGISTRY in nal_ingest.py and gis_ingest.py
- `cama_ingest.py` retained — do not delete until Escambia testing confirmed.

---

## parcel_sale_history Table

- Stores full ownership chain per parcel from county PA scrape.
- Distinct from sales_comps (SDF-sourced qualified arm's-length only).
- Unique constraint: `uq_psh_county_parcel_sale` on
  (county_fips, parcel_id, sale_date, grantor, grantee).
- grantor/grantee NOT NULL DEFAULT '' — empty string used in place of NULL
  to ensure unique constraint fires correctly on missing names.

---

## Scraping / Robots Policy

- Tier 1 government sources (RealForeclose, RealTaxDeed, LandmarkWeb):
  file-drop parsers — robots.txt blocks live scraping on all three.
- `public.escambiaclerk.com`: generic crawlers permitted; ClaudeBot blocked
  by name. Behind Cloudflare — Playwright required, requests blocked.
- Scraper auto-discovery via `real_invest_fl/scrapers/` package imports.

---

## Beds / Baths

- Populated opportunistically on parcel match from any listing source.
- `bed_bath_source` tracks provenance.
- Never overwrite an existing value with a lower-confidence source.
  Logic lives in the parser layer.

---

## Signal Tiers

- Signal tier reflects delivery source, not underlying event type.
- A foreclosure on Zillow is Tier 3; same event from Escambia Clerk is Tier 1.

---

## Subscription and Access Model

- County is the fundamental unit of access control and monetization.
- Subscription tiers: single county, regional bundle, statewide, enterprise.
- First bundle: Pensacola Metro = Escambia (12033) + Santa Rosa (12113).
- First expansion county: Santa Rosa (FIPS 12113).
- User-county authorization: `user_county_access` join table.
- County access enforced via single reusable FastAPI dependency — not at
  the application layer.
- Multi-user from day one. No single-admin stub acceptable.

---

## Filter Profile Model

- Profiles scoped to county_fips.
- System profiles: user_id = NULL, visible to all authorized users,
  not editable or deletable by users.
- Users clone a system profile to create a private editable copy.
  "Save as my profile" is a first-class UI action.
- User profiles: user_id = owner, private, fully editable.
- Uniqueness enforced via two partial unique indexes (live in DB, v0.13):
  - System: UNIQUE (county_fips, profile_name) WHERE user_id IS NULL
  - User: UNIQUE (user_id, county_fips, profile_name) WHERE user_id IS NOT NULL
- Cross-county profiles deferred to Phase 3+.

### Filter Profile Unique Constraint Verification
```sql
-- Verify both partial unique indexes are live on filter_profiles:
SELECT conname FROM pg_constraint
WHERE conrelid = 'filter_profiles'::regclass AND contype = 'u';
-- Expected: two rows — one for system profiles, one for user profiles```

---

## Scoring and Filter Enforcement Model

- passed_filters, filter_rejection_reasons, deal_score computed at query time
  against standing inventory — NOT at ingest time.
- deal_score_version tracks algorithm version for auditability.
- Filter profile save/modify triggers background recompute of listing_events
  for that county_fips — Phase 4 dependency.
- API routes sort and filter on pre-computed columns only.

---

## Auth Model

- JWT HS256 via PyJWT. sub = users.id as string. email included as display
  hint only — never used for identity lookup.
- Token payload: sub, email, type="access", iat, exp.
- Password hashing: bcrypt direct. passlib dropped — incompatible with
  bcrypt 4.0+/5.0.0.
- get_current_user: decodes JWT, extracts user id, loads User from DB,
  raises 401 on failure or inactive user.
- require_county_access: superuser bypass, otherwise checks
  user_county_access for (user_id, county_fips) row, raises 403 on denial.
- Auth routes: POST /auth/token, GET /auth/me only.
  Registration, password reset, user management deferred to Phase 4.

---

## Windows / Python Platform Notes

- Windows / Python 3.13 strptime: use `%b` (abbreviated) not `%B` (full).
  Escambia Clerk pages deliver abbreviated month names. `%B` fails silently.

---

## Workflow Patterns

- Zillow workflow: --dry-run first to surface [REVIEW] items, then live run.
  Standard for all attended file-drop parsers.
- Long-running processes in dedicated PowerShell windows are approved pattern.
- Machine runs 24/7.

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
```python
ROOT = Path(__file__).resolve().parent.parent.parent  # adjust per table
sys.path.insert(0, str(ROOT))
from config.settings import settings
from sqlalchemy import create_engine, text
engine = create_engine(settings.sync_database_url)```

---

## Schema Reference

### properties (confirmed 2026-05-04)
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
id                        INTEGER       PK
county_fips               VARCHAR(5)    NOT NULL
parcel_id                 VARCHAR(30)   NOT NULL
listing_type              VARCHAR(50)
list_price                INTEGER
list_date                 DATE
expiry_date               DATE
days_on_market            INTEGER
source                    VARCHAR(100)
listing_url               VARCHAR(1000)
listing_agent_name        VARCHAR(200)
listing_agent_email       VARCHAR(200)
listing_agent_phone       VARCHAR(30)
mls_number                VARCHAR(50)             -- no unique constraint
price_per_sqft            NUMERIC(8,2)
arv_estimate              INTEGER
arv_source                VARCHAR(20)
rehab_cost_estimate       INTEGER
arv_spread                INTEGER
zestimate_value           INTEGER
zestimate_discount_pct    NUMERIC(6,3)
zestimate_fetched_at      TIMESTAMPTZ
deal_score                NUMERIC(5,4)
deal_score_version        VARCHAR(20)
deal_score_components     JSONB
filter_profile_id         INTEGER
passed_filters            BOOLEAN
filter_rejection_reasons  JSONB
workflow_status           VARCHAR(30)   NOT NULL
notes                     TEXT
raw_listing_json          JSONB
scraped_at                TIMESTAMPTZ
created_at                TIMESTAMPTZ   NOT NULL  default now()
updated_at                TIMESTAMPTZ   NOT NULL  default now()
signal_tier               INTEGER
signal_type               VARCHAR(50)
Indexes: listing_events_pkey, ix_le_county_parcel, ix_le_deal_score,
         ix_le_listing_type, ix_le_status, ix_le_signal_tier,
         ix_le_signal_type
		 
### users (v0.13)
id               INTEGER       PK autoincrement
email            VARCHAR(255)  NOT NULL UNIQUE
hashed_password  VARCHAR(255)  NOT NULL
full_name        VARCHAR(200)  nullable
is_active        BOOLEAN       NOT NULL default true
is_superuser     BOOLEAN       NOT NULL default false
created_at       TIMESTAMPTZ   NOT NULL default now()
updated_at       TIMESTAMPTZ   NOT NULL default now()

### user_county_access (v0.13)
id                  INTEGER      PK autoincrement
user_id             INTEGER      NOT NULL FK → users.id ON DELETE CASCADE
county_fips         VARCHAR(5)   NOT NULL FK → counties.county_fips
granted_at          TIMESTAMPTZ  NOT NULL default now()
granted_by_user_id  INTEGER      nullable FK → users.id ON DELETE SET NULL
UNIQUE (user_id, county_fips)

### subscription_bundles (v0.13)
id           INTEGER       PK autoincrement
bundle_name  VARCHAR(100)  NOT NULL UNIQUE
description  VARCHAR(500)  nullable
is_active    BOOLEAN       NOT NULL default true
created_at   TIMESTAMPTZ   NOT NULL default now()

### bundle_counties (v0.13)
bundle_id    INTEGER     NOT NULL FK → subscription_bundles.id ON DELETE CASCADE
county_fips  VARCHAR(5)  NOT NULL FK → counties.county_fips
PRIMARY KEY (bundle_id, county_fips)

### parcel_sale_history (v0.14, v0.15)
id           INTEGER      PK autoincrement
county_fips  VARCHAR(5)   NOT NULL
parcel_id    VARCHAR(30)  NOT NULL
sale_date    DATE
sale_price   INTEGER
grantor      VARCHAR(200) NOT NULL DEFAULT ''
grantee      VARCHAR(200) NOT NULL DEFAULT ''
instrument   VARCHAR(100)
book         VARCHAR(20)
page         VARCHAR(20)
created_at   TIMESTAMPTZ  NOT NULL default now()
UNIQUE (county_fips, parcel_id, sale_date, grantor, grantee)
  -- uq_psh_county_parcel_sale

### data_source_status (v0.12)
source       VARCHAR(100)  NOT NULL  PK
county_fips  VARCHAR(5)    NOT NULL  PK
last_run_at  TIMESTAMPTZ
last_status  VARCHAR(50)
last_count   INTEGER
notes        TEXT
