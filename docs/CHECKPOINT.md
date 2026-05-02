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
**Repo:** stratyne/real_invest_fl (private)
**Local path:** D:\Chris\Documents\Stratyne\real_invest_fl
**Python:** 3.13.5 | **Venv:** .venv | **Editor:** VSCodium 1.112.01907
**DB container:** Docker — `real_invest_db`
**DB verification:** Docker `psql` against `real_invest_db`
(localhost:5432, user penstock, db real_invest_fl)

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
listing" and capture the list price.

**The existing `stratyne/pensacola_invest_bot` repo is a separate deliverable.
Never reference or merge it.**

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

## Migration Chain (HEAD = f7a8b9c0d1e2)

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

---

## Data Counts (verified 2026-04-27)

| Dataset | Count | Notes |
|---|---|---|
| NAL ingest | 70,994 qualified / 99,567 rejected | ingest_run_id=12 |
| GIS ingest | 160,264 rows updated | 2,478 unmatched |
| ARV calculation | 70,994 rows | avg ARV $198,833, avg jv_per_sqft $112.25 |
| Lis pendens | 101 records | 90-day backfill Jan 27 – Apr 23 2026 |
| Foreclosure events | 7 records | May 2026 manual pull |
| Tax deed events | 5,730 records | 2019-01-07 – 2026-12-02; historical backfill complete |
| Auction.com listings | 11 records | 2026-04-28 initial load |
| Zillow listings | 218 records | 13 foreclosures + 205 for-sale, 2026-04-28 |

---

## CAMA Status

Full run (70k+ parcels) hit timeout errors. Beds/baths NOT available from
ECPA CAMA detail page — populated opportunistically from listing sources.
Full CAMA enrichment deferred — not required for POC.

---

## Pending Actions (priority order)

1. **[PARTIAL]** Beds/baths opportunistic population in place. Bulk source pending, not a blocker.
2. **[COMPLETE]** Address normalization — `normalize_street_address()` built, 50 tests passing. See REFERENCE.md.
3. **[COMPLETE]** `listing_matcher.py` architectural resolution — scrapers route through centralized pipeline. See REFERENCE.md.
4. **[COMPLETE]** `data_source_status` table — live UI source-status board. Migration `e5f6a7b8c9d0`. See REFERENCE.md.
5. **[COMPLETE]** User/tenant model — auth infrastructure, JWT, county access enforcement. Migration `f7a8b9c0d1e2`. 115 tests passing. See REFERENCE.md.
6. **[NEXT]** Phase 4 UI — FastAPI + React (Vite) + MapLibre GL JS. Full detail in REFERENCE.md Item 6.
7. **[PENDING]** Deal scoring engine — weighted score on ARV spread, discount to list, signal tier, DOM.
8. **[PENDING]** Daily scheduler — Windows Task Scheduler → master runner script.
9. **[PENDING]** Zestimate integration — RapidAPI Zillow wrapper, rate-limited, MQI-matched only.
10. **[PENDING]** Output pipeline — Google Sheets export.
11. **[PENDING]** Email/outreach pipeline — auto-generated outreach email, logged.
12. **[PENDING]** HUD Home Store scraper — monitor until listings appear.
13. **[PENDING]** File FL DOR multi-year SDF request — PTOTechnology@floridarevenue.com.
14. **[PENDING]** Await Ch. 119 response from Escambia County Clerk.
15. **[PENDING]** Annual NAL/CAMA refresh pipeline — Phase 3.
16. **[PENDING]** Subscription sources — Landvoice, REDX, PropStream — Phase 3.
17. **[DEFERRED]** Craigslist FSBO scraper — effort/reward too high.
18. **[DEFERRED]** Full CAMA enrichment — timeout issue, not POC-critical.
19. **[DEFERRED]** NAV data ingest.
20. **[DEFERRED]** SDF comp engine.

---

## PM Rules (Locked — Never Override)

- Critical at every step — no shortcuts, no silent assumptions, no tunnel vision
- Do NOT assume file contents, paths, or schema details not explicitly provided
- If a file path or file content is needed, ASK before writing code
- All design decisions documented before code is written
- Checkpoint updated at end of every session
- Repo stays private — competitive sensitivity is real
- Old repo (pensacola_invest_bot) is a separate deliverable — never reference or merge
- Conventional Commits: feat:, fix:, chore:, docs:, test:, refactor:
- Reference REFERENCE.md for locked design decisions, schema detail,
  file paths, scraper notes, and completed item archives before asking

