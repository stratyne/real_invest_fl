# Project Penstock — CHECKPOINT.md

**OPENING PROMPT FOR EVERY NEW CHAT SESSION:**
"Due to chat length and token cost, I am starting a fresh chat to help continue
the following project. This is a real-world assignment. This is NOT an exercise.
There are real world repercussions for failure or wasted effort. DO NOT assume
in order to appease me or make the process go faster. If you don't know a file
path, ASK. If you don't know the code in a file that you need to revise or edit,
I will gladly share it with you. Do you understand the seriousness of the situation?"

---

## Project Identity

**Name:** Project Penstock
**Repo:** stratyne/real_invest_fl (private)
**Local path:** D:\Chris\Documents\Stratyne\real_invest_fl
**Python:** 3.13.5 | **Venv:** .venv | **Editor:** VSCodium 1.112.01907
**DB container:** Docker — `real_invest_db`
**DB verification:** Docker `psql` against `real_invest_db` (localhost:5432, user penstock, db real_invest_fl)

---

## Project Origin

Penstock began as a single SOW requesting a daily automated bot to find,
filter, rank, and schedule appointments for high-potential investment
properties in Pensacola/Escambia County FL.

The SOW criteria represent the first concrete user story and proof-of-concept 
filter profile. They will be satisfied as a natural outcome of building the 
platform. The Strategic Vision — not the SOW — defines the product.

Core criteria from that SOW that remain active:

- **Location:** Pensacola, Escambia County FL only (ZIPs 32501-32514, 32526, 32534, etc.)
- **Max list price:** $225,000
- **Property type:** Single-family residential only
- **Bedrooms:** exactly 3 | **Bathrooms:** exactly 2
- **Foundation:** slab only
- **Construction:** cinder block / concrete block, 1950-present
- **Year built:** 1950 or later
- **Data sources (priority order):** FSBO, bank-owned/REO/foreclosure, expired MLS,
  Zillow, Redfin, Realtor.com, Homes.com, FSBO.com, Foreclosure.com, Auction.com,
  public foreclosure aggregators
- **Daily outputs:** Google Sheet or CSV, Zestimate cross-reference, discount %,
  price/sqft, rehab estimate, ARV spread, sorted by price ascending
- **Outreach:** auto-generated email to agents with Calendly link, one-click send,
  logged responses
- **Scheduler:** GitHub Actions, AWS Lambda, or cron
- **Notifications:** email or Discord on failure

The original SOW specified SQLite, Selenium, and a monolithic single-repo
design. All three were superseded before development began. Current
architecture (PostgreSQL, Playwright, modular pipeline) is locked and takes
precedence over the SOW on all technical decisions.

**The existing `stratyne/pensacola_invest_bot` repo is a separate deliverable.
Never reference or merge it.**

---

## Strategic Vision

Penstock is a private, inventory-first real estate investment property discovery
and scoring platform for Florida, with Escambia County (Pensacola) as the
proof-of-concept. It builds a Master Qualified Inventory (MQI) of every
pre-screened parcel from free public government data (FL DOR NAL, SDF, CAMA,
GIS), then matches incoming distress signals and listing events against that
standing inventory. Long-term goal: statewide platform covering all 67 FL
counties, competing commercially with PropStream.

The hybrid model is inventory-first: the MQI is built once from government data,
then listing sources are used only to confirm "this MQI parcel has an active
listing" and capture the list price. This is a fundamentally lighter and lower-risk
scraping task than discovery-first scraping of commercial listing sites.

---

## Phase Structure

**Phase 1 — Foundation and Full Inventory** ← COMPLETE
NAL ingest, CAMA enrichment, GIS ingest, ARV calculation, SDF comps, seed data.

**Phase 2 — Scraping and Daily Matching** ← ACTIVE
Core scraping framework, address normalization, parcel matching, and staging
parsers complete. Remaining: daily scheduler, output channels.
Transitioning to Phase 4 UI in parallel.

**Phase 3 — Subscription Sources and CAMA Refresh**
Landvoice, REDX, PropStream modules. Annual NAL/CAMA refresh pipeline.

**Phase 4 — UI**
FastAPI + React (Vite) + MapLibre GL JS. Filter profile management, ranked
property list, map view, outreach template generation, one-click email send
with Calendly/Google Calendar link, full outreach log.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.13.5 |
| Web framework | FastAPI + Uvicorn |
| Database | PostgreSQL 16 + PostGIS 3.4 (Docker) |
| ORM / Migrations | SQLAlchemy 2.x async + Alembic |
| Sync DB access | SQLAlchemy create_engine (sync) via settings.sync_database_url |
| Data handling | Pandas + PyArrow |
| Scraping | requests + BeautifulSoup (permitted, non-JS-gated sites); Playwright (JS-gated or Cloudflare-protected sites) |
| Config | Pydantic v2 BaseSettings + python-dotenv |
| Email | SendGrid / Gmail SMTP |
| Calendar | Google Calendar OAuth2 |
| Sheets | Google Sheets API (service account) |
| Notifications | Telegram + Discord webhook |
| UI framework | FastAPI + React (Vite) + MapLibre GL JS |
| Containerization | Docker + docker-compose |

---

## Migration Chain (complete, HEAD = e5f6a7b8c9d0)

54c4159dbf59 v0.2 initial schema — 14 tables
4ca6031e21c4 v0.3 NAL rename
f422169456bd v0.4 replace scalar with JSON filter
5381f80387ed v0.5 zoning, nav_total_assessment, alt_key index
390bc7eab733 v0.6 ingest_runs full implementation
25a1f5163f3b v0.7 county_zips foreign key
a1b2c3d4e5f6 v0.8 widen own_state VARCHAR(2) → VARCHAR(25)
b2c3d4e5f6a7 v0.9 add jv_per_sqft, arv_estimate, arv_spread, list_price to properties
c3d4e5f6a7b8 v0.10 add signal_tier (INT), signal_type (VARCHAR 50) to listing_events
d4e5f6a7b8c9 v0.11 add bed_bath_source VARCHAR(50) to properties
e5f6a7b8c9d0 v0.12 add data_source_status table

---

## Data Counts (verified 2026-04-27)

| Dataset | Count | Notes |
|---|---|---|
| NAL ingest | 70,994 qualified / 99,567 rejected | ingest_run_id=12 |
| GIS ingest | 160,264 rows updated | 2,478 unmatched |
| ARV calculation | 70,994 rows | avg ARV $198,833, avg jv_per_sqft $112.25 |
| Lis pendens | 101 records | 90-day backfill Jan 27 – Apr 23 2026 |
| Foreclosure events | 7 records | May 2026 manual pull |
| Tax deed events | 5,730 records | 2019-01-07 – 2026-12-02; 4,394 redeemed; 1 null price (malformed source row); historical backfill complete |
| Auction.com listings  | 11 records | 2026-04-28 initial load |
| Zillow listings | 218 records | 13 foreclosures (2026-04-28 initial load) + 205 for-sale (2026-04-28) |

---

## CAMA Status

Full run (70k+ parcels) hit timeout errors. Limited to ~100 parcels per manual
batch. `raw_cama_json` contains only `zoning` key — no sales history. Full
enrichment deferred; not required for POC. Bedrooms and bathrooms are NOT
available from the ECPA CAMA detail page — source TBD. Beds/baths are being 
populated opportunistically from listing sources. Full CAMA enrichment deferred — 
not required for POC.

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
- Parcel ID normalization: strip non-alphanumeric, uppercase, NO zero-padding.
  `properties.parcel_id` is stored as 16 chars. `normalize_parcel_id()` in
  `parcel_id.py` zero-pads to 18 — do NOT call it in scrapers; it will break
  the join. Use raw strip+uppercase only.

### Street Address Normalization
- `normalize_street_address()` in `real_invest_fl/utils/text.py` is the
  single shared street normalizer for all scrapers and listing_matcher.
  Transformations (in order): upper-case, unit strip, digit-letter
  injection (ordinals excluded), suffix abbreviation, directional contraction.
  50 tests passing as of 2026-04-28.
- Digit-letter injection uses `(\d)(?!(?:ST|ND|RD|TH)\b)([A-Z])` to
  exclude ordinal suffixes (74TH, 48TH) from splitting.
- Unit stripping runs BEFORE digit-letter injection so that compound
  unit values like SUITE 2A are consumed whole before 2A is split.
- `#` unit designator has no leading `\b` anchor — `#` is not a word
  character and `\b` before it never fires.
- `listing_matcher._normalize_address()` is a thin delegation wrapper
  to `normalize_street_address()`. Call sites are unchanged.
- Address matching uses a three-level fallback: exact match, unit suffix
  normalization (#4A → 4A), street prefix with MULTI-UNIT review flag.
- Address normalization library: rapidfuzz v3.14.5

### Scraping / Robots
- Tier 1 government sources (RealForeclose, RealTaxDeed, LandmarkWeb) are
  file-drop parsers — robots.txt blocks live scraping on all three
- `public.escambiaclerk.com` (generic crawlers permitted) is scrapeable
  by application code; ClaudeBot specifically is disallowed by name
- `public.escambiaclerk.com` is behind Cloudflare — requests is blocked
  regardless of User-Agent; Playwright is required
- Scraper auto-discovery via `real_invest_fl/scrapers/` package imports

### Per-Scraper Implementation Notes
- `_normalize_street()` in `auction_com.py` is intentionally minimal — only
  digit-letter space injection and upper/collapse. Do not expand it further.
  Auction_com.py and zillow_parser.py are now wired through lookup_parcel_by_address() 
  in listing_matcher.py. 110 FRISCO ROAD, 5931 MULDOON ROAD, and 3640 WELLINGTON ROAD 
  resolved after centralization. 2983 NORTH HIGHWAY 95 A remains unmatched — normalizes 
  to 2983 N HWY 95 A; suspected NAL storage format mismatch, not a normalization pipeline defect.
- Auction.com GraphQL API: POST https://graph.auction.com/graphql. No
  authentication required. x-cid header must be a fresh UUID per request.
  $hasAuthenticatedUser variable must be removed from both the operation
  signature and variables — server rejects unused variables.
  Query captured 2026-04-28.
- Auction.com returns 50-mile radius results (~73 records). Filter to
  country_primary_subdivision=FL AND country_secondary_subdivision=ESCAMBIA
  (case-insensitive). Only 14-17 records survive the filter.
- `total_bedrooms=0` and `total_bathrooms=0` in Auction.com data are
  missing-data sentinels, not real values. Treat as None.
- Data table on `taxsaleMobile.asp` is nested inside an outer wrapper table.
  Select it with `soup.find("table", attrs={"bgcolor": "#0054A6"})` —
  never `soup.find("table")` which returns the wrong table.
- zillow_parser.py accepts mixed listing types (foreclosure, house for sale, FSBO,
  auction, active). listing_type and signal_type are derived from the specs line
  suffix, not hardcoded. Falls back to 'foreclosure' constant if unparseable.
- normalize_street_address() accepts strip_unit=False to preserve unit designators
  for _lookup_parcel() Level 2 unit normalization. _extract_street() in
  zillow_parser.py uses strip_unit=False. _normalize_address() uses default
  strip_unit=True (dedup key only, not passed to DB lookup).
- _extract_zip() anchors to end of address string (\b(\d{5})\s*$) to avoid
  matching 5-digit house numbers like 11150 before the ZIP.  

### Beds / Baths
- Beds/baths populated opportunistically on parcel match from any listing source.
  `bed_bath_source` tracks provenance. Never overwrite an existing value with a
  lower-confidence source — that logic lives in the parser layer.

### Signal Tiers
- Signal tier reflects the delivery source, not the underlying event type.
  A foreclosure on Zillow is Tier 3; the same event from the Escambia Clerk
  is Tier 1.

### Workflow Patterns
- Zillow workflow: --dry-run first to surface [REVIEW] items, then live run.
  This is the standard workflow for all attended file-drop parsers.
- Long-running processes in dedicated PowerShell windows are approved pattern
- Machine runs 24/7

### Windows / Python Platform Notes
- Windows / Python 3.13 strptime: use `%b` (abbreviated month name) not `%B`
  (full month name). The Escambia Clerk pages deliver abbreviated month names.
  `%B` fails silently on Windows Python 3.13.

### Subscription and Access Model (Locked)
- County is the fundamental unit of access control and monetization.
- Subscription tiers: single county, regional bundle, statewide, custom
  multi-county (enterprise).
- Regional bundles are predefined multi-county groupings reflecting real
  investment markets. First bundle: Pensacola Metro = Escambia (12033) +
  Santa Rosa (12113). Future: Miami Metro, Tampa Metro, Orlando Metro, etc.
- First expansion county: Santa Rosa (FIPS 12113).
- User-county authorization is a join table (user_county_access).
  Middleware enforces county access on every API request via a single
  reusable FastAPI dependency — not enforced at the application layer.
- Multi-user from day one. Full auth infrastructure required in Phase 4.
  No single-admin stub acceptable.

### Filter Profile Model (Locked)
- Filter profiles are scoped to county_fips.
- System catalog profiles: user_id = NULL, visible to all users authorized
  for that county, not editable or deletable by users.
- System profiles serve as baseline seeds. Users clone a system profile to
  create a private editable copy — "Save as my profile" is a first-class
  UI action.
- User-created profiles: user_id = owner, private, fully editable.
- Cross-county filter profiles deferred to Phase 3+. POC uses single-county
  profiles only.

### Scoring and Filter Enforcement Model (Locked)
- passed_filters, filter_rejection_reasons, and deal_score are computed
  at insert/update time in the ingest pipeline — not at query time.
- deal_score computed on insert/update. deal_score_version tracks the
  scoring algorithm version for auditability.
- When a user saves or modifies a filter profile, existing listing_events
  records for that county_fips must be re-evaluated. A background recompute
  job is required — this is a Phase 4 dependency that must be designed
  before the filter profile save/clone UI is built.
- API routes sort and filter on pre-computed columns only — no on-the-fly
  scoring at query time.

---

## ROOT Path Bootstrap Rules

ROOT must resolve to the project root:
`D:\Chris\Documents\Stratyne\real_invest_fl\`

Correct `.parent` depth by file location:

| File location | ROOT expression |
|---|---|
| `scripts/*.py` | `Path(__file__).resolve().parent.parent` |
| `real_invest_fl/ingest/*.py` | `Path(__file__).resolve().parent.parent.parent` |
| `real_invest_fl/scrapers/*.py` | `Path(__file__).resolve().parent.parent.parent` |
| `real_invest_fl/ingest/staging_parsers/*.py` | `Path(__file__).resolve().parent.parent.parent.parent` |

The checkpoint boilerplate that previously showed `.parent.parent.parent.parent`
for all files was WRONG. Use the table above.

Standard bootstrap block:

```python
ROOT = Path(__file__).resolve().parent.parent.parent  # adjust depth per table above
sys.path.insert(0, str(ROOT))
from config.settings import settings
from sqlalchemy import create_engine, text
engine = create_engine(settings.sync_database_url)```

## Staging File-Drop Workflow

| Source | Staging folder | Format | Cadence |
|---|---|---|---|
| LandmarkWeb lis pendens | data/staging/lis_pendens/ | .xlsx | Weekly (export last 10 days) |
| RealForeclose foreclosures | data/staging/foreclosure/ | .csv (raw paste, 2-col key-value) | Weekly |
| Zillow listings | data/staging/zillow/ | .csv (manual copy/paste, one value per line) | Weekly |

Run after each drop:
python scripts/run_staging_import.py --source lis_pendens
python scripts/run_staging_import.py --source foreclosure
python scripts/run_staging_import.py --source zillow

Note: Tax deed data is sourced directly via the Escambia Clerk scraper
(`real_invest_fl/ingest/run_taxdeed.py`), not via file-drop. The
`data/staging/tax_deed/` folder and `tax_deed_parser.py` are retained
in case the Ch. 119 recurring export request is fulfilled.

## Escambia Clerk Tax Deed — Direct Scrape (COMPLETE)

public.escambiaclerk.com allows generic crawlers (robots.txt: Allow: / for User-agent: *). ClaudeBot is blocked by name but application code is not. Site is behind Cloudflare — Playwright required, requests blocked.

- Scraper: real_invest_fl/scrapers/escambia_taxdeed_clerk.py
- Runner: real_invest_fl/ingest/run_taxdeed.py
- Date list: https://public.escambiaclerk.com/taxsale/taxsaledates.asp
- Per-date detail: https://public.escambiaclerk.com/taxsale/taxsaleMobile.asp?saledate=M/D/YYYY
- saledate format: M/D/YYYY, no zero-padding, literal slashes — must NOT be percent-encoded; build URL as a string, do not use requests params dict
- Table selection: soup.find("table", attrs={"bgcolor": "#0054A6"})
- Table columns: Clerk File #, Account, Certificate Number, Reference (parcel ID), Sales Date, Status, Opening Bid Amount, Legal Description, Surplus Balance, Property Address
- Dedup key: listing_events.mls_number = Clerk File #; no unique constraint on mls_number — dedup via WHERE NOT EXISTS
- signal_tier=1, signal_type='tax_deed', source='escambia_clerk_taxsale'
- CLI: --historical (2019-present), --upcoming (today+), --date M/D/YYYY
- Historical backfill: complete — 5,730 records, 2019-01-07 through 2026-12-02
- Ongoing cadence: run --upcoming monthly after each sale date

python real_invest_fl/ingest/run_taxdeed.py --upcoming
python real_invest_fl/ingest/run_taxdeed.py --historical
python real_invest_fl/ingest/run_taxdeed.py --date 5/6/2026

## Scraper Source Tiers

| Tier | Sources | Approach | Status |
|---|---|---|---|
| 1 — Government direct | Escambia Clerk tax deed, lis pendens (LandmarkWeb), foreclosures (RealForeclose), RealTaxDeed | Live scrape or file-drop | Tax deed complete; others file-drop |
| 2 — Public aggregators | HUD Home Store, Foreclosure.com | Playwright + rate limiting | Auction.com COMPLETE; others pending |
| 3 — Free listing sources | Craigslist FSBO | requests + BS4 | Deferred indefinitely |
| 4 — Commercial platforms | Zillow, Redfin, Realtor.com, Homes.com | Paid API or vendor proxy | Deferred |

## Manual Source Investigation Results

- Tier 1 — Government Distress Records — already documented in checkpoint (tax deed scraper complete, lis pendens and foreclosure file-drop parsers in place)
- Tier 1 — Tax Delinquency Source Investigation Results (Manual, 2026-04-28)
	1. Escambia County Tax Collector — Delinquent Taxes https://escambiataxcollector.com/property-tax/delinquent/ The delinquent taxes page describes the process and links out to LienHub for tax deed applications and LienExpress for county-held certificate purchases. No bulk delinquent list is published directly on this page. The page itself is not a data source — it is a navigation hub.
	2. Escambia County Tax Certificate Search https://escambia.county-taxes.com/public General landing page only. No bulk delinquent list available for download. Dead end for programmatic or bulk data access.
	3. LienHub — Tax Deed Applications / Advertised List https://lienhub.com/county/escambia/portfolio/ Path: escambia.lienexpress.net → select county → Tax Lien Auction → spawns link to advertised list. The advertised list URL is: https://lienhub.com/county/escambia/certsale/main?unique_id=41C54840429511F1A2F69948A6B8334F&use_this=print_advertised_list The list is not yet published as of investigation date. Site message: "The Escambia County Tax Certificate Sale will be available May 5, 2026." This is the statutory May advertisement list — it will contain all delinquent parcels advertised per Florida Statute § 197.413. Check back after May 5, 2026 — this is a high-value bulk list.
	4. LienExpress — County-Held Certificates https://escambia.lienexpress.net/ This is the landing/redirect page that routes to LienHub for county-held certificate purchases. Not a standalone data source — functions as the entry point to LienHub.
- Tier 2 — Government Auction / Bulk Public Data Source Investigation Results (Manual, 2026-04-28)
	1. Escambia County Surplus Property Auctions https://myescambia.com/our-services/property-sales/surplus-property-auction Valid source. Zero active listings at time of investigation. Low volume expected by nature. Monitor periodically — no scraper warranted until listings appear. Flag for future check-back.
	2. HUD Home Store — Escambia County https://www.hudhomestore.gov/searchresult?citystate=FL Valid source. Zero active listings for Escambia County at time of investigation. Monitor periodically. No scraper warranted until listings appear.
	3. Auction.com — COMPLETE - Escambia County https://www.auction.com/residential/fl/escambia-county Valid source. 17 active listings at time of investigation (was 16 at initial checkpoint entry). Public search results visible without login. This is the next scrape investigation target. Need to determine: what property detail fields are available without an account, whether bot detection / JS rendering is required, and whether a structured scraper is feasible.
- Tier 3 — Commercial Listing Platforms / FSBO Source Investigation Results (Manual, 2026-04-28)
	1. Craigslist Pensacola Housing https://pensacola.craigslist.org/search/rea Valid source. Active listings present. Scraping is feasible technically (no login, public, requests + BS4 viable) but data will be messy — address visibility varies by poster, field structure is inconsistent across listings. Scraper is buildable but requires significant normalization work. Still in pending queue as originally planned.
	2. Zillow — Escambia County Foreclosures https://www.zillow.com/escambia-county-fl/foreclosures/ Valid source. 13 active listings at time of investigation. Fields visible without login: price, beds, baths, sqft, address, listing type (Foreclosure), agent/brokerage, days on market (some listings). Data quality is good — structured and consistent. Zillow anti-scraping posture is the primary obstacle (heavy JS, bot detection, API terms). Scraping approach TBD — RapidAPI Zillow wrapper is the approved POC approach per checkpoint. Deferred to Tier 4 commercial platform track.
	3. Facebook Marketplace — Pensacola Real Estate https://www.facebook.com/marketplace/pensacola/propertyforsale Valid source with active listings. Login required to view full listing detail. Not feasible for automated scraping — Playwright + authenticated session would be required, which introduces account risk and TOS violations. Designated manual-only source. No scraper to be built. No public RSS or feed alternative identified. Individual listing URLs contain tracking parameters but are publicly accessible when shared directly (confirmed by sample URL provided). Flag as monitor-only.

---

## Pending Actions (priority order)

1. **[PARTIALLY RESOLVED]** beds/baths now populated opportunistically from
   listing sources via bed_bath_source. Bulk sourcing from FL DOR NAL or
   ECPA still pending but not a blocker.

2. **[COMPLETE]** Address normalization layer —
   normalize_street_address() built and fully tested (50/50).
   strip_unit=False parameter added 2026-04-28. listing_matcher.py and
   zillow_parser.py both delegate to shared normalizer.
   strip_unit=False path bug fixed in text.py (2026-05-01): digit-letter 
   injection now confined to pre-unit portion when strip_unit=False, preventing 
   corruption of alphanumeric unit values (e.g. #4A). Two tests covering this path 
   added to tests/test_listing_matcher_lookup.py.

3. **[COMPLETE]** `listing_matcher.py` architectural resolution — `auction_com.py`
   and `zillow_parser.py` now route through `listing_matcher.py` centralized
   matching pipeline. Per-scraper `_lookup_parcel()` and bed/bath enrichment
   duplicates retired. Deterministic tests and live parity checks passed.
   Item 5 unblocked.

   Follow-ups:
   - Investigate unresolved Auction.com unmatched address: `2983 North Highway 95 A`
   - `auction_com.py` still not wired through `BaseScraper` discovery (out of scope here)
   - Parser-layer bed/bath confidence hierarchy still deferred

4. **[COMPLETE]** data_source_status table — live source-status board for UI
   status display. Schema, ORM model, model registration, shared status
   upsert helper, and runner integration are complete.

   Migration:
   - `e5f6a7b8c9d0` v0.12 add data_source_status table

   Verified behavior:
   - composite key `(source, county_fips)`
   - `last_success_at` updates only on SUCCESS
   - `last_run_at` reflects most recent completion / status update timestamp
   - FAILED preserves prior `last_success_at`
   - SUCCESS after FAILED clears `last_error_message`
   - invalid status raises `ValueError` before DB write
   - dry-run paths do not write status rows

   Integrated runners / dispatchers:
   - `real_invest_fl/ingest/run_taxdeed.py`
   - `real_invest_fl/ingest/run_auction_com.py`
   - `scripts/run_staging_import.py`

   Current source rows supported:
   - `escambia_clerk_taxsale`
   - `auction_com`
   - `zillow_foreclosure`
   - `escambia_landmarkweb`
   - `escambia_realforeclose`
   - `escambia_realtaxdeed`

5. **[NEXT]** User/tenant model — users table, user_county_access join table,
   subscription_bundles table with county constituents. Multi-user from day one.
   Full auth infrastructure required — no single-admin stub.
   Santa Rosa County (FIPS 12113) is the first expansion county.
   Pensacola Metro bundle (Escambia + Santa Rosa) is the first bundle.
   Required before Phase 4 UI work begins.

6. **[NEXT]** Phase 4 UI — FastAPI + React (Vite) + MapLibre GL JS.
   Filter profile management (system catalog + user clone + custom),
   ranked property list (pre-computed scores), map view, outreach template
   generation, one-click email send with Calendly/Google Calendar link,
   full outreach log. Multi-user, multi-county, subscription-gated.
   This is the product.
   Note: `data_source_status` is the live UI status board (one row per `(source, county_fips)`),
   separate from `ingest_runs`, which remains the append-only historical audit log.

7. **[PENDING]** Deal scoring engine — weighted score on ARV spread,
   discount to list, signal tier, days on market. Feeds the ranked
   list in the UI. Columns exist; logic not written.

8. **[PENDING]** Daily scheduler — Windows Task Scheduler entry pointing
   at master runner script.

9. **[PENDING]** Zestimate integration — RapidAPI Zillow wrapper, hitting
   only matched MQI properties, rate-limited. Enriches UI display.

10. **[PENDING]** Output pipeline — Google Sheets export. Secondary to UI
   but satisfies SOW daily output requirement.

11. **[PENDING]** Email/outreach pipeline — auto-generated outreach email
    per qualifying property, logged. Satisfies SOW outreach requirement.

12. **[PENDING]** HUD Home Store scraper (Tier 2) — hudhomestore.gov.
    Monitor until listings appear.

13. **[PENDING]** File Florida DOR multi-year SDF request —
    PTOTechnology@floridarevenue.com, Escambia County (No. 27),
    assessment years 2019-2024, CSV format.

14. **[PENDING]** Await Ch. 119 response from Escambia County Clerk re:
    recurring foreclosure/tax deed export.

15. **[PENDING]** Annual NAL/CAMA refresh pipeline — Phase 3.

16. **[PENDING]** Subscription sources — Landvoice, REDX, PropStream
    modules. Phase 3.

17. **[DEFERRED]** Craigslist FSBO scraper — effort/reward too high.
    Street addresses not available in structured data. Deferred
    indefinitely.

18. **[DEFERRED]** Full CAMA enrichment (70k parcels — timeout issue,
    not POC-critical).

19. **[DEFERRED]** NAV data ingest.

20. **[DEFERRED]** SDF comp engine.

---

## Relevant File Paths

real_invest_fl/                         <- project root
├── alembic/versions/                   <- all migration files
├── data/
│   ├── raw/                            <- NAL CSV, SDF CSV, GIS zips
│   └── staging/
│       ├── lis_pendens/
│       ├── foreclosure/
│       ├── tax_deed/
│       └── zillow/                     <- active
├── real_invest_fl/
│   ├── api/
│   │   ├── main.py
│   │   ├── deps.py
│   │   └── routes/                     <- approvals, config, counties, dashboard,
│   │                                      ingest, listings, outreach, properties
│   ├── db/
│   │   ├── models/
│   │   │   ├── data_source_status.py	<- ORM model for live per-source UI ingest status
│   │   │   ├── listing_event.py        <- includes signal_tier, signal_type
│   │   │   └── property.py
│   │   └── session.py
│   ├── ingest/
│   │   ├── arv_calculator.py
│   │   ├── cama_ingest.py
│   │   ├── enricher.py                 <- stub
│   │   ├── gis_ingest.py
│   │   ├── listing_matcher.py  		<- _normalize_address() now delegates
│   │   ├── nal_filter.py
│   │   ├── nal_ingest.py
│   │   ├── nal_loader.py
│   │   ├── nal_mapper.py
│   │   ├── rejected_parcels.py
│   │   ├── run_auction_com.py        <- COMPLETE
│   │   ├── run_context.py
│   │   ├── run_taxdeed.py              <- COMPLETE
│   │   ├── sdf_loader.py
│   │   ├── source_status.py 			<- shared upsert helper for data_source_status
│   │   └── staging_parsers/
│   │       ├── __init__.py
│   │       ├── foreclosure_parser.py
│   │       ├── lis_pendens_parser.py
│   │       ├── tax_deed_parser.py
│   │       └── zillow_parser.py              <- COMPLETE (renamed from zillow_foreclosure_parser.py)
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── auction_com.py          ← COMPLETE
│   │   ├── base_scraper.py
│   │   ├── escambia_foreclosure.py     <- robots-blocked, retained for future
│   │   └── escambia_taxdeed_clerk.py   <- COMPLETE
│   └── utils/
│       ├── parcel_id.py
│       ├── robots.py
│       └── text.py          ← normalize_street_address() added
└── scripts/
    ├── cold_start.py
	├── probe_auction_com.py                    ← investigation only
	├── probe_auction_com_request.py            ← investigation only
    ├── run_arv.py
    ├── run_staging_import.py
    └── seeds/
        ├── seed_counties.py
        ├── seed_county_zips.py
        └── seed_filter_profile.py

## listing_events Schema (confirmed 2026-04-27)

id                       INTEGER PK
county_fips              VARCHAR(5)  NOT NULL
parcel_id                VARCHAR(30) NOT NULL
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
mls_number               VARCHAR(50)        — no unique constraint
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
workflow_status          VARCHAR(30) NOT NULL
notes                    TEXT
raw_listing_json         JSONB
scraped_at               TIMESTAMPTZ
created_at               TIMESTAMPTZ NOT NULL  default now()
updated_at               TIMESTAMPTZ NOT NULL  default now()
signal_tier              INTEGER
signal_type              VARCHAR(50)
Indexes: listing_events_pkey, ix_le_county_parcel, ix_le_deal_score,
         ix_le_listing_type, ix_le_status
		 
## properties CAMA Schema (confirmed 2026-04-28)

foundation_type      VARCHAR(100)  nullable
exterior_wall        VARCHAR(100)  nullable
roof_type            VARCHAR(100)  nullable
bedrooms             INTEGER       nullable
bathrooms            NUMERIC(4,1)  nullable
bed_bath_source      VARCHAR(50)   nullable — provenance of bedrooms/bathrooms when populated from listing source e.g. 'zillow_foreclosure', 'craigslist',
                                             'manual'. Never overwrite existing value with lower-confidence source.
cama_quality_code    VARCHAR(10)   nullable
cama_condition_code  VARCHAR(10)   nullable
cama_enriched_at     TIMESTAMPTZ   nullable

## PM Rules (Locked — Never Override)

- Critical at every step — no shortcuts, no silent assumptions, no tunnel vision
- Do NOT assume file contents, paths, or schema details not explicitly provided
- If a file path or file content is needed, ASK before writing code
- All design decisions documented before code is written
- Checkpoint (this file) updated at end of every session
- Repo stays private — competitive sensitivity is real
- Old repo (pensacola_invest_bot) is a separate deliverable — never reference or merge
- Conventional Commits: feat:, fix:, chore:, docs:, test:, refactor: