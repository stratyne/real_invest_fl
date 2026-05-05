# Project Penstock — STATE.md
# Current project status only. No rationale. No design decisions.
# Updated: 2026-05-04

## Active Phase
**Phase 2** (scraping/matching) — core complete, scheduler/output pending.
**Phase 4** (UI) — starting next. Seed scripts must run first (items 11–12).
Phase 2 and Phase 4 run in parallel. Santa Rosa CAMA runs in background.

## Phase Summary

| Phase | Name | Status |
|---|---|---|
| 1 | Foundation and Full Inventory | SUBSTANTIALLY COMPLETE |
| 2 | Scraping and Daily Matching | ACTIVE — core complete, scheduler/output pending |
| 3 | Subscription Sources and CAMA Refresh | NOT STARTED |
| 4 | UI — FastAPI + React + MapLibre | NEXT — starting in parallel with Phase 2 tail |

**Phase 1 remaining:** CAMA enrichment (Santa Rosa in progress, Escambia site down).
All other Phase 1 work complete.

**Phase 3 scope:** Landvoice, REDX, PropStream modules. Annual NAL/CAMA refresh
pipeline. Multi-county CAMA architecture (each county PA has its own website —
no shared scraper possible).

**Phase 2 / Phase 4 parallel:** Santa Rosa CAMA runs in background. UI
development proceeds in parallel. Seed scripts (items 11–12) must clear first.

## Migration Chain
HEAD = i0j1k2l3m4n5 (v0.16)

| Rev | Version | Description |
|---|---|---|
| 54c4159dbf59 | v0.2 | initial schema — 14 tables |
| 4ca6031e21c4 | v0.3 | NAL rename |
| f422169456bd | v0.4 | replace scalar with JSON filter |
| 5381f80387ed | v0.5 | zoning, nav_total_assessment, alt_key index |
| 390bc7eab733 | v0.6 | ingest_runs full implementation |
| 25a1f5163f3b | v0.7 | county_zips foreign key |
| a1b2c3d4e5f6 | v0.8 | widen own_state VARCHAR(2) → VARCHAR(25) |
| b2c3d4e5f6a7 | v0.9 | add jv_per_sqft, arv_estimate, arv_spread, list_price |
| c3d4e5f6a7b8 | v0.10 | add signal_tier, signal_type to listing_events |
| d4e5f6a7b8c9 | v0.11 | add bed_bath_source to properties |
| e5f6a7b8c9d0 | v0.12 | add data_source_status table |
| f7a8b9c0d1e2 | v0.13 | user/tenant model — users, user_county_access, subscription_bundles, bundle_counties, filter_profiles.user_id, outreach_log.user_id, drop ui_sessions |
| g8h9i0j1k2l3 | v0.14 | add parcel_sale_history table |
| h9i0j1k2l3m4 | v0.15 | parcel_sale_history grantor/grantee NOT NULL DEFAULT '' |
| i0j1k2l3m4n5 | v0.16 | listing_scores table; strip scoring columns from listing_events |

**Note:** Ingest refactor (2026-05-02) produced NO migration — code only.
**Pending migration:** remove mqi_qualified, mqi_rejection_reasons,
mqi_qualified_at once Phase 4 query-time filter is live.

## Database State (verified 2026-05-04)

| County | FIPS | NAL rows | GIS geometry | CAMA enriched | Notes |
|---|---|---|---|---|---|
| Escambia | 12033 | 170,561 | 160,264 | 0 | dor_uc backfilled; escpa.org down |
| Santa Rosa | 12113 | 120,500 | 108,493 | 3,518 (running) | ~64,794 remaining |
| All others | — | staged only | staged only | 0 | NAL + GIS files in place |

**Total properties in DB:** 291,061
**parcel_sale_history:** 17,596+ rows (Santa Rosa only, growing)

## Historical POC Baseline (Escambia only — superseded 2026-05-02)
Retained as reference for backfill completeness verification.

| Dataset | Count | Notes |
|---|---|---|
| ARV calculation | 70,994 rows | avg ARV $198,833, avg jv_per_sqft $112.25 |
| Lis pendens | 101 records | 90-day backfill Jan 27 – Apr 23 2026 |
| Foreclosure events | 7 records | May 2026 manual pull |
| Tax deed events | 5,730 records | 2019-01-07 – 2026-12-02; historical backfill complete |
| Auction.com listings | 11 records | 2026-04-28 initial load |
| Zillow listings | 218 records | 13 foreclosures + 205 for-sale, 2026-04-28 |

## CAMA Run Status (2026-05-04)
- **Santa Rosa:** 3,518 / 68,312 enriched. Run in progress. ~42h remaining.
  Settings: delay 1.0–3.0s, REST_EVERY=500, REST_SECONDS=300.0
  Run is resumable — cama_enriched_at IS NULL filter skips processed parcels.
- **Escambia:** 0 enriched. escpa.org is DOWN. Do not attempt until confirmed up.
  When up: verify with `--limit 5 --dry-run` before any live run.

## Active Items

| # | Status | Description | Next Action |
|---|---|---|---|
| 1 | PARTIAL | Beds/baths opportunistic population | Bulk source pending — not a blocker |
| 13 | ACTIVE | Phase 4 UI — FastAPI + React + MapLibre | Outreach design session (schema + templates + send mechanism) → routes/outreach.py |
| 14 | PENDING | Statewide NAL ingest — 65 remaining counties | After Phase 4 scaffold |
| 15 | PENDING | Statewide GIS ingest — 65 remaining counties | After Phase 4 scaffold |
| 16 | IN PROGRESS | CAMA enrichment | Santa Rosa running; Escambia blocked |
| 17 | PENDING | arv_calculator.py refactor | Refactor into comp-based ARV engine using parcel_sale_history + NAL qual codes. mqi_qualified drift fix included. Santa Rosa: 4,884 qualified sales available. |
| 18 | PENDING | COUNTY_REGISTRY consolidation | Duplicated in nal_ingest.py + gis_ingest.py |
| 19 | PENDING | Deal scoring engine | Query-time only — no pre-computation job. |
| 20 | PENDING | Daily scheduler | Windows Task Scheduler → master runner script |
| 21 | PENDING | Zestimate integration | RapidAPI wrapper, rate-limited |
| 22 | PENDING | Output pipeline — Google Sheets export | — |
| 23 | PENDING | Email/outreach pipeline | Auto-generated outreach, logged |
| 24 | PENDING | HUD Home Store scraper | Monitor until listings appear |
| 26 | PENDING | Await Ch. 119 response — Escambia Clerk | — |
| 27 | PENDING | LienHub advertised list | Check 2026-05-05 — see URL in scrapers.md |
| 28 | PENDING | Annual NAL/CAMA refresh pipeline | Phase 3 |
| 29 | PENDING | Subscription sources — Landvoice, REDX, PropStream | Phase 3 |
| 36 | BLOCKED | routes/outreach.py | Requires: outreach_log full schema + migration, email_template seed + placeholder spec, send mechanism decision (SendGrid vs SMTP) |
| 37 | PENDING | counties.nal_last_ingested_at / cama_last_ingested_at not updated by ingest pipeline | Investigate nal_ingest.py — add update to counties row on successful ingest completion |

## Deferred Items
| # | Description | Reason |
|---|---|---|
| 25 | FL DOR multi-year SDF request | Downgraded — parcel_sale_history + NAL qual codes sufficient for ARV engine. SDF improves comp pool but is not required. PTOTechnology@floridarevenue.com when prioritized. |
| 30 | Craigslist FSBO scraper | Effort/reward too low |
| 31 | Full CAMA enrichment statewide | Phase 3 — each county needs own scraper |
| 32 | NAV data ingest | Deferred |

## Completed Items (summary — detail in DECISIONS.md and context/ files)
| # | Description | Completed |
|---|---|---|
| 2 | Address normalization | 2026-04-28 |
| 3 | listing_matcher.py architectural resolution | 2026-04-28 |
| 4 | data_source_status table (v0.12) | 2026-04-28 |
| 5 | User/tenant model + auth infrastructure (v0.13) | 2026-04-28 |
| 6 | Ingest pipeline refactor — full multi-county | 2026-05-02 |
| 7 | Statewide NAL staging — all 67 counties | 2026-05-02 |
| 8 | Statewide GIS staging — all 67 counties | 2026-05-02 |
| 9 | Santa Rosa NAL ingest — 120,500 rows | 2026-05-04 |
| 10 | Santa Rosa GIS ingest — 108,493 rows | 2026-05-02 |
| 11 | seed_superuser.py — superuser created, Escambia access granted | 2026-05-04 |
| 12 | seed_bundles.py — pensacola_metro bundle seeded, Santa Rosa activated | 2026-05-04 |
| 33 | parcel_sale_history table (v0.14, v0.15) | 2026-05-04 |
| 34 | Multi-county CAMA framework | 2026-05-04 |
| 35 | Phase 4 API scaffold — deps.py, main.py, all route stubs implemented except outreach | 2026-05-04 |