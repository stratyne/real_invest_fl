# Project Penstock — CHECKPOINT_v2.0.md

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
**Repo:** stratyne/real_invest_fl (public)
- GitHub requires login to view the repo despite it being public. You need to try the raw content URLs directly.
**Local path:** D:\Chris\Documents\Stratyne\real_invest_fl
**Python:** 3.13.5 | **Venv:** .venv | **Editor:** VSCodium 1.112.01907
**DB container:** Docker — `real_invest_db`
**DB verification:** Docker `psql` against `real_invest_db`
(localhost:5432, user penstock, db real_invest_fl)
docker exec -it real_invest_db psql -U penstock -d real_invest_fl -c "SELECT conname FROM pg_constraint WHERE conrelid = 'filter_profiles'::regclass AND contype = 'u';"

---

## Strategic Vision

Penstock is a multi-user, inventory-first real estate investment property
discovery and scoring platform for Florida. It ingests the complete public
property tax roll for every Florida county — every parcel, every use code,
no filtering at ingest time — and stores it as a clean, queryable inventory.
Users build and manage their own filter models that run against that shared
inventory at query time. No two users need the same criteria. The inventory
supports all of them.

Long-term goal: statewide platform covering all 67 FL counties, competing
commercially with PropStream. Escambia County (Pensacola) is the
proof-of-concept.

The original SOW (single investor, single county, hardcoded criteria,
Google Sheet output) is ONE example of what a single user's filter profile
produces against this platform. It is not the architecture. It is a test case.

**The existing `stratyne/pensacola_invest_bot` repo is a separate deliverable.
Never reference or merge it.**

---

## Phase Structure

**Phase 1 — Foundation and Full Inventory** ← SUBSTANTIALLY COMPLETE
NAL ingest (all 67 counties staged), GIS ingest (all 67 counties staged),
CAMA enrichment (Escambia only, partial — site down), ARV calculation,
seed data. Multi-county ingest pipeline fully refactored.

**Phase 2 — Scraping and Daily Matching** ← ACTIVE
Core scraping framework, address normalization, parcel matching, and staging
parsers complete. Remaining: daily scheduler, output channels.
Transitioning to Phase 4 UI in parallel.

**Phase 3 — Subscription Sources and CAMA Refresh**
Landvoice, REDX, PropStream modules. Annual NAL/CAMA refresh pipeline.
Multi-county CAMA architecture (each county has its own property appraiser
website — no shared URL pattern).

**Phase 4 — UI** ← NEXT
FastAPI + React (Vite) + MapLibre GL JS. Filter profile management, ranked
property list, map view, outreach template generation, one-click email send
with Calendly/Google Calendar link, full outreach log. Multi-user,
multi-county, subscription-gated.

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
| Scraping | requests + BeautifulSoup; Playwright (JS-gated / Cloudflare) |
| Config | Pydantic v2 BaseSettings + python-dotenv |
| Auth | PyJWT + bcrypt (direct) + python-multipart |
| Email | SendGrid / Gmail SMTP |
| Calendar | Google Calendar OAuth2 |
| Sheets | Google Sheets API (service account) |
| Notifications | Telegram + Discord webhook |
| UI framework | React (Vite) + MapLibre GL JS |
| Containerization | Docker + docker-compose |

---

## Migration Chain (HEAD = h9i0j1k2l3m4)

54c4159dbf59  v0.2   initial schema — 14 tables
4ca6031e21c4  v0.3   NAL rename
f422169456bd  v0.4   replace scalar with JSON filter
5381f80387ed  v0.5   zoning, nav_total_assessment, alt_key index
390bc7eab733  v0.6   ingest_runs full implementation
25a1f5163f3b  v0.7   county_zips foreign key
a1b2c3d4e5f6  v0.8   widen own_state VARCHAR(2) → VARCHAR(25)
b2c3d4e5f6a7  v0.9   add jv_per_sqft, arv_estimate, arv_spread, list_price
c3d4e5f6a7b8  v0.10  add signal_tier, signal_type to listing_events
d4e5f6a7b8c9  v0.11  add bed_bath_source to properties
e5f6a7b8c9d0  v0.12  add data_source_status table
f7a8b9c0d1e2  v0.13  user/tenant model — users, user_county_access,
                      subscription_bundles, bundle_counties,
                      filter_profiles.user_id, outreach_log.user_id,
                      drop ui_sessions
g8h9i0j1k2l3  v0.14  add parcel_sale_history table
h9i0j1k2l3m4  v0.15  parcel_sale_history grantor/grantee NOT NULL DEFAULT ''

The ingest refactor (2026-05-02) produced NO migration. It is code-only.
A future migration will remove mqi_qualified, mqi_rejection_reasons, and
mqi_qualified_at once Phase 4 query-time filter is live.

---

## Database State (verified 2026-05-02)

| County | FIPS | NAL rows | GIS geometry | CAMA enriched | Notes |
|---|---|---|---|---|---|
| Escambia | 12033 | 170,561 | 160,264 | 0 | dor_uc backfilled to 3-digit; site down |
| Santa Rosa | 12113 | 120,500 | 108,493 | 3,518 (in progress) | 64,794 remaining |
| All others | — | staged only | staged only | 0 | NAL CSVs + GIS shapefiles in place |

Total properties in DB: 291,061
parcel_sale_history: 17,596+ rows (Santa Rosa, growing)
All 67 county NAL CSVs staged under canonical folder structure.
All 67 county GIS shapefiles staged under canonical folder structure.
Miami-Dade has two shapefiles (main + condos). Saint Johns condos zip
contained .dbf only — no .shp, no action required.
dor_uc normalized to zero-padded three digits for all ingested counties.
Escambia dor_uc backfilled via direct SQL UPDATE 2026-05-04.
Santa Rosa NAL re-ingested 2026-05-04 with normalized dor_uc.

### Pre-2026-05-02 POC data counts (Escambia only, now superseded)
| Dataset | Count | Notes |
|---|---|---|
| ARV calculation | 70,994 rows | avg ARV $198,833, avg jv_per_sqft $112.25 |
| Lis pendens | 101 records | 90-day backfill Jan 27 – Apr 23 2026 |
| Foreclosure events | 7 records | May 2026 manual pull |
| Tax deed events | 5,730 records | 2019-01-07 – 2026-12-02; historical backfill complete |
| Auction.com listings | 11 records | 2026-04-28 initial load |
| Zillow listings | 218 records | 13 foreclosures + 205 for-sale, 2026-04-28 |

---

## CAMA Status

### Escambia (12033)
Previous run wrote zoning to 1,399 parcels (dor_uc = '001') but
cama_enriched_at was never set — confirmed 2026-05-02. All remaining
CAMA fields are NULL for those 1,399 parcels. Full re-scrape of all
106,372 dor_uc = '001' Escambia parcels required when escpa.org comes
back online. Verify with --limit 5 --dry-run before any live run.

escpa.org was down as of 2026-05-02. Do not attempt live CAMA ingest
until confirmed back up.

Scraper: real_invest_fl/ingest/cama/escambia.py
Runner: python -m real_invest_fl.ingest.cama.escambia [options]
Rate limiting: DEFAULT_DELAY=1.5, DEFAULT_DELAY_MAX=4.0,
               REST_EVERY=100, REST_SECONDS=270.0 (empirically tested)
cama_ingest.py retained — do not delete until Escambia testing confirmed.

Beds/baths NOT available from ECPA CAMA detail page.
Sale history NOT available from ECPA CAMA detail page — captured
separately via escambia_taxdeed_clerk.py and staging parsers.

### Santa Rosa (12113)
Scraper: real_invest_fl/ingest/cama/santa_rosa.py
Runner: python -m real_invest_fl.ingest.cama.santa_rosa [options]
Data source: https://parcelview.srcpa.gov/?parcel={parcel_id}&baseUrl=http://srcpa.gov/
Server-rendered HTML. No JavaScript, auth, or cookies required.
Rate limiting: DEFAULT_DELAY=1.0, DEFAULT_DELAY_MAX=3.0,
               REST_EVERY=500, REST_SECONDS=300.0
No robots.txt on either srcpa.gov or parcelview.srcpa.gov.
Soft-block confirmed at ~2,859 requests over ~1h54m at 1.0-3.0s delay
with no rest pauses. REST_EVERY=500/REST_SECONDS=300.0 added as mitigation.
Soft-block signature: HTTP 200 with disclaimer-only response body
(residentialBuildingsContainer absent). Scraper stops cleanly on detection.
Run is fully resumable — cama_enriched_at IS NULL filter skips
already-processed parcels automatically.

Status as of 2026-05-04: 3,518/68,312 enriched, run in progress.
Target: 68,312 dor_uc = '001' parcels.
Estimated remaining runtime at current settings: ~42 hours.

Sale history captured from same parcelview page per request.
parcel_sale_history populated with full ownership chain per parcel.

### Multi-county CAMA architecture
Each county property appraiser has a different website, URL pattern,
and HTML structure. No shared scraper is possible.

Shared framework: real_invest_fl/ingest/cama/base.py
  - coerce_building() — returns (coerced, null_cols) tuple
  - coerce_sale()
  - fetch_qualified_parcels() — target_dor_ucs county-supplied
  - write_cama() — writes non-None values; explicitly NULLs guard-rejected fields
  - write_sales() — upserts to parcel_sale_history, idempotent
  - run() / main() — all rate-limiting params county-supplied, no defaults

County modules supply: COUNTY_FIPS, SOURCE_NAME, HEADERS,
TARGET_DOR_UCS, DEFAULT_DELAY, DEFAULT_DELAY_MAX, REST_EVERY,
REST_SECONDS, fetch_page(), parse_building(), parse_sales()

New county checklist:
  1. Check robots.txt at county PA domain
  2. Inspect parcel page HTML structure
  3. Determine rate limit empirically (start conservative)
  4. Create real_invest_fl/ingest/cama/{county_snake}.py
  5. Add to COUNTY_REGISTRY in nal_ingest.py and gis_ingest.py

---

## Pending Actions (priority order)

1. **[PARTIAL]** Beds/baths opportunistic population in place. Bulk
   source pending, not a blocker.
2. **[COMPLETE]** Address normalization. See REFERENCE.md.
3. **[COMPLETE]** listing_matcher.py architectural resolution. See REFERENCE.md.
4. **[COMPLETE]** data_source_status table. Migration e5f6a7b8c9d0. See REFERENCE.md.
5. **[COMPLETE]** User/tenant model — auth infrastructure, JWT, county
   access enforcement. Migration f7a8b9c0d1e2. 115 tests passing. See REFERENCE.md.
6. **[COMPLETE]** Ingest pipeline refactor — nal_ingest.py and
   gis_ingest.py fully multi-county. --county-fips required CLI arg.
   Canonical path resolution. Filter logic removed from ingest.
   mqi nullification complete for all Escambia rows. dor_uc normalized
   to zero-padded three digits in nal_mapper.py (_dor_uc() helper).
   Escambia dor_uc backfilled via direct SQL UPDATE 2026-05-04.
7. **[COMPLETE]** Statewide NAL staging — all 67 county NAL CSVs staged.
8. **[COMPLETE]** Statewide GIS staging — all 67 county GIS shapefiles staged.
9. **[COMPLETE]** Santa Rosa NAL ingest — 120,500 rows. Re-ingested 2026-05-04 with normalized dor_uc.
10. **[COMPLETE]** Santa Rosa GIS ingest — 108,493 rows with geometry.
11. **[PENDING — BLOCKER]** Run seed_superuser.py — required before Phase 4 auth can be tested.
12. **[PENDING — BLOCKER]** Run seed_bundles.py — seeds Pensacola Metro bundle, activates Santa Rosa county access.
13. **[NEXT]** Phase 4 UI — FastAPI + React (Vite) + MapLibre GL JS.
    Seed scripts (items 11-12) must run first. Santa Rosa CAMA ingest runs in background — UI development proceeds in parallel.
14. **[PENDING]** Statewide NAL ingest — 65 remaining counties.
15. **[PENDING]** Statewide GIS ingest — 65 remaining counties.
16. **[IN PROGRESS]** CAMA enrichment — Santa Rosa 3,518/68,312 complete, run in progress. Escambia pending escpa.org recovery.
17. **[PENDING]** arv_calculator.py — same mqi_qualified drift as
    cama_ingest.py. Needs refactor before use.
18. **[PENDING]** COUNTY_REGISTRY consolidation — currently duplicated
    in nal_ingest.py and gis_ingest.py. Should live in one shared module.
19. **[PENDING]** Deal scoring engine — weighted score on ARV spread,
    discount to list, signal tier, DOM.
20. **[PENDING]** Daily scheduler — Windows Task Scheduler → master
    runner script.
21. **[PENDING]** Zestimate integration — RapidAPI Zillow wrapper,
    rate-limited, MQI-matched only.
22. **[PENDING]** Output pipeline — Google Sheets export.
23. **[PENDING]** Email/outreach pipeline — auto-generated outreach
    email, logged.
24. **[PENDING]** HUD Home Store scraper — monitor until listings appear.
25. **[PENDING]** File FL DOR multi-year SDF request —
    PTOTechnology@floridarevenue.com.
26. **[PENDING]** Await Ch. 119 response from Escambia County Clerk.
27. **[PENDING]** LienHub advertised list — check on 2026-05-05.
    https://lienhub.com/county/escambia/certsale/main
    ?unique_id=41C54840429511F1A2F69948A6B8334F
    &use_this=print_advertised_list
28. **[PENDING]** Annual NAL/CAMA refresh pipeline — Phase 3.
29. **[PENDING]** Subscription sources — Landvoice, REDX, PropStream
    — Phase 3.
30. **[DEFERRED]** Craigslist FSBO scraper — effort/reward too high.
31. **[DEFERRED]** Full CAMA enrichment statewide — Phase 3, each
    county requires its own scraper.
32. **[DEFERRED]** NAV data ingest.

---

## PM Rules (Locked — Never Override)

- The platform serves infinite users with infinite use cases. The
  original SOW is one user's one filter profile — not the architecture.
- Critical at every step — no shortcuts, no silent assumptions, no
  tunnel vision
- Do NOT assume file contents, paths, or schema details not explicitly
  provided
- If a file path or file content is needed, ASK before writing code
- All design decisions documented before code is written
- Checkpoint updated at end of every session
- Old repo (pensacola_invest_bot) is a separate deliverable — never
  reference or merge
- Conventional Commits: feat:, fix:, chore:, docs:, test:, refactor:
- Reference REFERENCE.md for locked design decisions, schema detail,
  file paths, scraper notes, and completed item archives before asking
- When in doubt about scope or direction, ask — do not assume
