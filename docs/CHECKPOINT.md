# Project Penstock — CHECKPOINT.md

> **OPENING PROMPT FOR EVERY NEW CHAT SESSION:**
> "Due to chat length and token cost, I am starting a fresh chat to help continue
> the following project. This is a real-world assignment. This is NOT an exercise.
> There are real world repercussions for failure or wasted effort. DO NOT assume
> in order to appease me or make the process go faster. If you don't know a file
> path, ASK. If you don't know the code in a file that you need to revise or edit,
> I will gladly share it with you. Do you understand the seriousness of the
> situation?"

---

## Project Identity

**Name:** Project Penstock
**Repo:** stratyne/real_invest_fl (private)
**Local path:** D:\Chris\Documents\Stratyne\real_invest_fl
**Python:** 3.13.5 | **Venv:** .venv | **Editor:** VSCodium 1.112.01907
**DB GUI:** DBeaver Community (localhost:5432, user penstock, db real_invest_fl)
**DB container:** Docker — `real_invest_db`

---

## Project Origin

Penstock began as a single SOW requesting a daily automated bot to find,
filter, rank, and schedule appointments for high-potential investment
properties in Pensacola/Escambia County FL. Core criteria from that SOW
that remain active:

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

---

## Phase Structure (Locked)

**Phase 1 — Foundation and Full Inventory** ← current phase
NAL ingest, CAMA enrichment, GIS ingest, ARV calculation, SDF comps, seed data.

**Phase 2 — Scraping and Daily Matching** ← active development
Modular scraper framework, address normalization, fuzzy parcel matching,
listing_events population, staging file-drop parsers, daily scheduler,
output channels (Google Sheets, email, Telegram).

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
| Scraping | requests + BeautifulSoup (permitted sites); Playwright reserved for JS-gated sites |
| Config | Pydantic v2 BaseSettings + python-dotenv |
| Email | SendGrid / Gmail SMTP |
| Calendar | Google Calendar OAuth2 |
| Sheets | Google Sheets API (service account) |
| Notifications | Telegram + Discord webhook |
| UI framework | FastAPI + React (Vite) + MapLibre GL JS |
| Containerization | Docker + docker-compose |

---

## Migration Chain (complete, HEAD = c3d4e5f6a7b8)

54c4159dbf59 v0.2 initial schema — 14 tables
4ca6031e21c4 v0.3 NAL rename
f422169456bd v0.4 replace scalar with JSON filter
5381f80387ed v0.5 zoning, nav_total_assessment, alt_key index
390bc7eab733 v0.6 ingest_runs full implementation
25a1f5163f3b v0.7 county_zips foreign key
a1b2c3d4e5f6 v0.8 widen own_state VARCHAR(2) → VARCHAR(25)
b2c3d4e5f6a7 v0.9 add jv_per_sqft, arv_estimate, arv_spread, list_price to properties
c3d4e5f6a7b8 v0.10 add signal_tier (INT), signal_type (VARCHAR 50) to listing_events

---

## Data Counts (verified)

| Dataset | Count | Notes |
|---|---|---|
| NAL ingest | 70,994 qualified / 99,567 rejected | ingest_run_id=12 |
| GIS ingest | 160,264 rows updated | 2,478 unmatched |
| ARV calculation | 70,994 rows | avg ARV $198,833, avg jv_per_sqft $112.25 |
| Lis pendens | 101 records | 90-day backfill Jan 27 – Apr 23 2026 |
| Foreclosure events | 7 records | May 2026 manual pull |
| Tax deed events | 10 records | May 2026 manual pull |

---

## CAMA Status

Full run (70k+ parcels) hit timeout errors. Limited to ~100 parcels per manual
batch. `raw_cama_json` contains only `zoning` key — no sales history. Full
enrichment deferred; not required for POC. Bedrooms and bathrooms are NOT
available from the ECPA CAMA detail page — source TBD.

---

## Key Design Decisions (Locked)

- ARV proxy = `jv` (Just Value from NAL) until multi-year SDF comps available
- Signal model is primary; traditional listing model is a parallel track
- Tier 1 government sources (RealForeclose, RealTaxDeed, LandmarkWeb) are
  file-drop parsers — robots.txt blocks live scraping on all three
- `public.escambiaclerk.com` (generic crawlers permitted) is scrapeable
  by application code; ClaudeBot specifically is disallowed by name
- `listing_events` is the unified output table for all signal and listing sources
- Scraper auto-discovery via `real_invest_fl/scrapers/` package imports
- Address normalization: `real_invest_fl/utils/text.py` + rapidfuzz (v3.14.5)
- Parcel ID normalization: `real_invest_fl/utils/parcel_id.py` (18-char, zero-padded)
- Session pattern: async (`settings.database_url`) for ORM;
  sync (`settings.sync_database_url`) for batch scripts
- All SQL in batch scripts uses `text()` — never raw string SQL
- CAST(:raw_listing_json AS jsonb) — never ::jsonb in text() statements
- SDF deferred; NAV deferred until deal-scoring is approved deliverable
- DBeaver selected as permanent DB GUI
- Long-running processes in dedicated PowerShell windows are approved pattern
- Machine runs 24/7

---

## DB Connection Pattern (batch scripts)

```python
ROOT = Path(__file__).resolve().parent.parent.parent.parent
from config.settings import settings
from sqlalchemy import create_engine, text
engine = create_engine(settings.sync_database_url)```

## Staging File-Drop Workflow
| Source | Staging folder | Format | Cadence |
|---|---|---|---|
| LandmarkWeb lis pendens | data/staging/lis_pendens/ | .xlsx |Weekly (export last 10 days) |
| RealForeclose foreclosures | data/staging/foreclosure/ | .csv (raw paste, 2-col key-value) | Weekly |
| RealTaxDeed tax deeds | data/staging/tax_deed/ | .csv (raw paste, 2-col key-value) | Monthly |
Run after each drop:
python scripts/run_staging_import.py --source lis_pendens
python scripts/run_staging_import.py --source foreclosure
python scripts/run_staging_import.py --source tax_deed

## Escambia Clerk Tax Deed — Direct Scrape (Permitted)

`public.escambiaclerk.com` allows generic crawlers (robots.txt: Allow: / for
User-agent: *). ClaudeBot is blocked by name but application code is not.

- Date list: https://public.escambiaclerk.com/taxsale/taxsaledates.asp
  (270+ dates back to 10/4/1999, through 12/2/2026)
- Per-date listings: https://public.escambiaclerk.com/taxsale/taxsaleMobile.asp?saledate=M/D/YYYY
- Table columns: Clerk File #, Account, Certificate Number, Reference (parcel ID),
  Sales Date, Status, Opening Bid Amount, Legal Description, Surplus Balance,
  Property Address
- Dedup key: `listing_events.mls_number` = Clerk File #
- signal_tier=1, signal_type='tax_deed', source='escambia_clerk_taxsale'

**This scraper has NOT been written yet. It is the next build target.**

---

## Pending Actions (priority order)

1. **[NEXT]** Write `real_invest_fl/scrapers/escambia_taxdeed_clerk.py` and
   `scripts/run_taxdeed_scraper.py` — scrapes taxsaledates.asp for date list,
   then fetches each taxsaleMobile.asp page, parses the HTML table, matches
   by Reference (parcel ID), inserts into listing_events. CLI flags:
   `--historical` (2019-present), `--upcoming` (future dates only),
   `--date M/D/YYYY` (single date). Rate limit: 3-6 second random delay.

2. **[PENDING]** File Florida DOR multi-year SDF request -
   PTOTechnology@floridarevenue.com, Escambia County (No. 27),
   assessment years 2019-2024, CSV format.

3. **[PENDING]** Await Ch. 119 response from Escambia County Clerk re:
   recurring foreclosure/tax deed export.

4. **[PENDING]** Craigslist Pensacola FSBO scraper (Tier 3) -
   pensacola.craigslist.org/search/rea, simple requests + BS4, no bot detection.

5. **[PENDING]** HUD Home Store scraper (Tier 2) - hudhomestore.gov.

6. **[PENDING]** `data_source_status` table - tracks last ingest timestamp
   per source for UI status display. Add before UI work begins.

7. **[PENDING]** User/tenant model - required before Phase 4 UI work begins.

8. **[PENDING]** Output pipeline - Google Sheets export, email automation,
   deal scoring engine.

9. **[DEFERRED]** Full CAMA enrichment (70k parcels - timeout issue,
   not POC-critical).

10. **[DEFERRED]** NAV data ingest.

11. **[DEFERRED]** SDF comp engine.

---

## Relevant File Paths

real_invest_fl/
├── alembic/versions/               ← all migration files
├── data/
│   ├── raw/                        ← NAL CSV, SDF CSV, GIS zips, LandmarkWeb xlsx
│   └── staging/
│       ├── lis_pendens/
│       ├── foreclosure/
│       └── tax_deed/
├── real_invest_fl/
│   ├── api/
│   │   ├── main.py
│   │   ├── deps.py
│   │   └── routes/                 ← approvals, config, counties, dashboard,
│   │                                  ingest, listings, outreach, properties
│   ├── db/
│   │   ├── models/
│   │   │   ├── listing_event.py    ← includes signal_tier, signal_type
│   │   │   └── property.py
│   │   └── session.py
│   ├── ingest/
│   │   ├── arv_calculator.py
│   │   ├── cama_ingest.py
│   │   ├── enricher.py             ← stub
│   │   ├── gis_ingest.py
│   │   ├── listing_matcher.py
│   │   ├── nal_filter.py
│   │   ├── nal_ingest.py
│   │   ├── nal_loader.py
│   │   ├── nal_mapper.py
│   │   ├── rejected_parcels.py
│   │   ├── run_context.py
│   │   ├── sdf_loader.py
│   │   └── staging_parsers/
│   │       ├── __init__.py
│   │       ├── foreclosure_parser.py
│   │       ├── lis_pendens_parser.py
│   │       └── tax_deed_parser.py
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── base_scraper.py
│   │   └── escambia_foreclosure.py ← robots-blocked, retained for future
│   └── utils/
│       ├── parcel_id.py
│       ├── robots.py
│       └── text.py
└── scripts/
    ├── cold_start.py
    ├── run_arv.py
    ├── run_staging_import.py
    └── seeds/
        ├── seed_counties.py
        ├── seed_county_zips.py
        └── seed_filter_profile.py

## PM Rules (Locked — Never Override)

- Critical at every step — no shortcuts, no silent assumptions, no tunnel vision
- Do NOT assume file contents, paths, or schema details not explicitly provided
- If a file path or file content is needed, ASK before writing code
- All design decisions documented before code is written
- Checkpoint (this file) updated at end of every session
- Repo stays private — competitive sensitivity is real
- Old repo (pensacola_invest_bot) is a separate deliverable — never reference or merge
- Conventional Commits: feat:, fix:, chore:, docs:, test:, refactor: