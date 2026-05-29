# Project Penstock — STATE.md
# Current project status only. No rationale. No design decisions.
# Updated: 2026-05-28

## Active Phase
**Phase 2** (scraping/matching) — core complete, scheduler/output pending.
**Phase 4** (UI) — active. Deployment complete. Tail items pending.
Phase 2 and Phase 4 run in parallel.
Both CAMA runs ACTIVE.

## Phase Summary

| Phase | Name | Status |
|---|---|---|
| 1 | Foundation and Full Inventory | SUBSTANTIALLY COMPLETE |
| 2 | Scraping and Daily Matching | ACTIVE — core complete, scheduler/output pending |
| 3 | Subscription Sources and CAMA Refresh | NOT STARTED |
| 4 | UI — FastAPI + React + MapLibre | ACTIVE — dashboard flow complete, map pins live |

**Phase 1 remaining:** CAMA enrichment (Santa Rosa in progress, Escambia in progress).
All other Phase 1 work complete.

**Phase 3 scope:** Landvoice, REDX, PropStream modules. Annual NAL/CAMA refresh
pipeline. Multi-county CAMA architecture (each county PA has its own website —
no shared scraper possible).

**Phase 2 / Phase 4 parallel:** Both CAMA runs active in background.
UI development proceeds in parallel.

## Migration Chain
HEAD = n5o6p7q8r9s0 (v0.21) — live and verified

| Rev | Version | Description |
|---|---|---|
| 54c4159dbf59 | v0.2 | initial schema — 14 tables (includes property_value_history, sales_comps) |
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
| j1k2l3m4n5o6 | v0.17 | Phase 4 outreach schema — outreach_templates, skip_trace_cache, outreach_log (stub → full), users.calendar_link |
| k2l3m4n5o6p7 | v0.18 | user_profile_prefs |
| l3m4n5o6p7q8 | v0.19 | multi-county filter profiles — county_fips VARCHAR(5)[] |
| m4n5o6p7q8r9 | v0.20 | listing_events workflow_status CHECK constraint |
| n5o6p7q8r9s0 | v0.21 | add arv_source to properties |

**Note:** Ingest refactor (2026-05-02) produced NO migration — code only.
**Note:** alembic/env.py updated 2026-05-26 to use HOST_SYNC_DATABASE_URL — required for host-side migration runs.
**Pending migration:** remove mqi_qualified, mqi_rejection_reasons,
mqi_qualified_at once Phase 4 query-time filter is live.

## Database State (verified 2026-05-28)

| County | FIPS | NAL rows | GIS geometry | CAMA enriched | Notes |
|---|---|---|---|---|---|
| Escambia | 12033 | 170,561 | 160,264 | ~18,448 | Live CAMA run active. beds/baths/quality absent from parcelcard. ARV run pending sufficient enrichment. |
| Santa Rosa | 12113 | 120,500 | 111,036 | ~67,041 | ARV second pass complete — 67,595 COMP / 52,905 JV_FALLBACK. CAMA run complete. |
| All others | — | staged only | staged only | 0 | NAL + GIS files in place |

**Total properties in DB:** 291,061

**parcel_sale_history (verified 2026-05-28):**

| Metric | Escambia | Santa Rosa |
|---|---|---|
| Enriched parcels | 18,448 | 67,041 |
| Parcels with sales | 18,321 | 66,750 |
| Total sale records | 84,140 | 150,484 |

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

## CAMA Run Status (updated 2026-05-28)
- **Santa Rosa:** Second pass RUNNING. 2,265 retry parcels (dor_uc '001' only).
  54,453 unenriched parcels are non-SFR dor_uc — will not be scraped.
  Resumable via cama_enriched_at IS NULL.
- **Escambia:** RUNNING via scripts/run_escambia_cama.py. ~18,448 / 106,372 enriched.
  Soft-block rate limiting active — wrapper cycling at 420s intervals.
  beds/baths/cama_quality_code absent from Escambia parcelcard — will remain NULL.
  Resumable via cama_enriched_at IS NULL.

## Active Items

| # | Status | Description | Next Action |
|---|---|---|---|
| 1 | PARTIAL | Beds/baths opportunistic population for Escambia County | Bulk source pending — not a blocker |
| 14 | PENDING | Statewide NAL ingest — 65 remaining counties | After Phase 4 scaffold |
| 15 | PENDING | Statewide GIS ingest — 65 remaining counties | After Phase 4 scaffold |
| 16 | IN PROGRESS | CAMA enrichment | Santa Rosa complete. Escambia live run active (~18,448 enriched, soft-block rate limiting in progress). |
| 17 | PARTIAL | arv_calculator.py refactor | Santa Rosa second pass complete — 67,595 COMP / 52,905 JV_FALLBACK / 120,500 updated. Escambia --force run pending sufficient CAMA enrichment. |
| 18 | PENDING | COUNTY_REGISTRY consolidation | Duplicated in nal_ingest.py + gis_ingest.py — do not touch during other work |
| 20 | PENDING | Daily scheduler | Windows Task Scheduler → master runner script |
| 21 | PENDING | Zestimate integration | RapidAPI wrapper, rate-limited |
| 22 | PENDING | Output pipeline — Google Sheets export | — |
| 23 | PENDING | Email/outreach pipeline | Auto-generated outreach, logged |
| 24 | PENDING | HUD Home Store scraper | Monitor until listings appear |
| 26 | PENDING | Await Ch. 119 response — Escambia Clerk | — |
| 27 | PENDING | LienHub advertised list | Check 2026-05-05 — see URL in scrapers.md |
| 28 | PENDING | Annual NAL/CAMA refresh pipeline | Phase 3 |
| 29 | PENDING | Subscription sources — Landvoice, REDX, PropStream | Phase 3 |
| 95 | PENDING | Split Dockerfile into Dockerfile.api / Dockerfile.worker / Dockerfile.scraper — eliminate Playwright from API and worker images, pandas/geopandas from API image. Requires pyproject.toml dependency group split. | After Phase 4 tail items complete |
| 116 | PENDING | bed_bath_source enforcement in parser layer — confidence hierarchy logic. Never overwrite higher-confidence source with lower. Design fully specified in arv.md. Blocked on nothing — ready to implement when prioritized. | — |
| 122 | PENDING | absentee_owner population — NULL for all 291,061 properties in both counties. Computation never implemented in NAL ingest pipeline. Must be derived at ingest time by comparing owner mailing address to property address. Affects absentee_owner filter and absentee_score deal scoring dimension. | Implement in nal_ingest.py or as a post-ingest update script. |

## Deferred Items

| # | Description | Reason |
|---|---|---|
| 25 | FL DOR multi-year SDF request | Downgraded — parcel_sale_history + NAL qual codes sufficient for ARV engine. SDF improves comp pool but is not required. PTOTechnology@floridarevenue.com when prioritized. |
| 30 | Craigslist FSBO scraper | Effort/reward too low |
| 31 | Full CAMA enrichment statewide | Phase 3 — each county needs own scraper |
| 32 | NAV data ingest | Deferred |
| 44 | Skip-trace live integration | BatchData API wrapper, credit/billing model, DNC compliance. Schema scaffold in place (v0.17). Unblock after Phase 4 outreach flow is live. |
| 91 | Map pins — colored markers by signal tier | Post-deployment polish. Custom Marker children required. |
| 92 | Map pins — auto-fit bounds to pageResults on page change | Low demo value with single-region data. Revisit when multi-region. |
| 103 | Local dev environment setup not documented — vite proxy port, docker-compose ports mapping, npm run dev workflow | Will cause repeated confusion when returning to local dev after a gap |
| 105 | Search architecture — Option A migration (full SQL ORDER BY / LIMIT / OFFSET) | Prerequisite: deal scoring engine (item 19) must be stable enough to express score as a SQL expression. Option C is the correct interim state. |
| 106 | SalesComp ORM model and sales_comps table exist but have no ingest pipeline and no relationship on Property. Placeholder for FL DOR SDF (item 25). No action until item 25 is prioritized. |
| 115 | arv_calculator.py Phase 3 scaling — per-parcel spatial query ~120ms/parcel acceptable for 2-county scope. County-wide bulk join attempted and failed at Santa Rosa scale. Revisit at Phase 3 with temp table pre-aggregation or partitioned bulk join. | Phase 3 |

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
| 10 | Santa Rosa GIS ingest — 111,036 rows (corrected; run completed 2026-05-15) | 2026-05-15 |
| 11 | seed_superuser.py — superuser created, Escambia access granted | 2026-05-04 |
| 12 | seed_bundles.py — pensacola_metro bundle seeded, Santa Rosa activated | 2026-05-04 |
| 13 | Phase 4 UI — dashboard flow complete, map pins live, deployment complete | 2026-05-23 |
| 19 | Deal scoring engine — deal_score_weights round-trip complete. Weights hydrated from profile, passed through filterStateToPayload. dom_score dimension added. Hardcoded weights removed. | 2026-05-28 |
| 33 | parcel_sale_history table (v0.14, v0.15) | 2026-05-04 |
| 34 | Multi-county CAMA framework | 2026-05-04 |
| 35 | Phase 4 API scaffold — deps.py, main.py, all route stubs implemented except outreach | 2026-05-04 |
| 37 | counties.nal_last_ingested_at and cama_last_ingested_at stamps added | 2026-05-26 |
| 38 | seed_outreach_templates.py — system EMAIL + LETTER templates seeded | 2026-05-04 |
| 39 | ORM models — OutreachTemplate, SkipTraceCache, OutreachLog, calendar_link, back-populates patches | 2026-05-12 |
| 40 | Pydantic schemas — outreach inline in routes/outreach.py | 2026-05-12 |
| 41 | routes/outreach.py — generate, send, list, skip_trace. All 4 routes confirmed in Swagger UI. | 2026-05-12 |
| 42 | users.calendar_link — Pydantic + route exposure | 2026-05-14 |
| 43 | settings.py additions — BATCHDATA_API_KEY, SKIP_TRACE_CACHE_TTL_DAYS, BUSINESS_ADDRESS | 2026-05-14 |
| 45 | v0.17 migration — Phase 4 outreach schema live and verified | 2026-05-05 |
| 46 | seed_demo_account.py — demo superuser, Escambia + Santa Rosa access, calendar_link set | 2026-05-14 |
| 47 | React frontend scaffold — Vite + TypeScript, axios client, API types, LoginPage, DashboardPage, ResultsPage | 2026-05-14 |
| 48 | Docker deployment — Cloudflare Tunnel + Nginx + Uvicorn, stratyne.com/app | 2026-05-23 |
| 50 | Server-side pagination — PaginatedPropertySearchResult envelope; page/page_size on both search routes; Python-side slice after scoring; last_result_count upsert uses total (pre-page) | 2026-05-23 |
| 51 | Documentation — phase4_ui.md, DECISIONS.md, schema.md rewrite; REFERENCE.md + CHECKPOINT.md deleted | 2026-05-14 |
| 52 | v0.18 migration — user_profile_prefs table | 2026-05-14 |
| 53 | ORM model — UserProfilePrefs | 2026-05-14 |
| 54 | routes/dashboard.py — get_dashboard rewrite to profile activity + outreach pipeline status | 2026-05-14 |
| 55 | routes/profiles.py — toggle_favorite implemented | 2026-05-15 |
| 56 | v0.19 migration — multi-county filter profiles, county_fips VARCHAR(5)[] | 2026-05-15 |
| 57 | DashboardPage.tsx rewrite; SearchPage.tsx extracted; App.tsx updated; ResultsPage.tsx import fix | 2026-05-14 |
| 58 | Deal score weights editor — Deal Score Weights section in SearchPage with four NumInput fields and live weight sum indicator. | 2026-05-28 |
| 59 | Frontend multi-county refactor — types/api.ts, SearchPage.tsx, DashboardPage.tsx, ResultsPage.tsx, profiles.ts, api/properties.ts, App.tsx route updated to /results (profileId moved to nav state) | 2026-05-15 |
| 60 | Seed script audit — seed_bundles.py, seed_demo_account.py clean, no changes needed | 2026-05-15 |
| 69 | Backend multi-county route contract refactor — routes/profiles.py de-county-scoped (flat /profiles prefix); routes/properties.py search profile-driven via /properties?filter_profile_id= and POST /properties/search; routes/dashboard.py county_fips returns string[] | 2026-05-15 |
| 70 | Map pins — lat/lng added to PropertySearchResult schema + both search route construction loops | 2026-05-15 |
| 71 | user_profile_prefs upsert — last_result_count bug resolved; upsert placement confirmed correct | 2026-05-15 |
| 72 | price_reduced filter — removed from FilterState, EMPTY_FILTER, profileToFilterState, filterStateToPayload, countActiveFilters, and Search UI. No backend handler existed. Deferred pending listing_events.price_reduced column + scraper wiring. | 2026-05-23 |
| 73 | PropertyValueHistory ORM relationship on Property — confirmed real model, real table (created v0.2). Append-only annual value log, populated by annual NAL refresh pipeline (item 28). Not a POC artifact. | 2026-05-26 |
| 74 | Star/favorite toggle wired in DashboardPage.tsx — toggleFavorite call on star click, optimistic update | 2026-05-15 |
| 75 | phase4_ui.md route table — profiles prefix corrected to flat /profiles | 2026-05-15 |
| 76 | ORM model gap — zoning, nav_total_assessment, jv_per_sqft, arv_estimate, arv_spread, list_price added to property.py | 2026-05-15 |
| 77 | county_nos sub-filter removed — FilterState, filterStateToPayload, _apply_filters, SearchPage UI | 2026-05-15 |
| 78 | StatementTooComplexError fix — tuple IN() replaced with county-scoped fetch + Python key filter in both search routes | 2026-05-15 |
| 79 | arv_estimate fallback — (ev.arv_estimate if ev else None) or prop.arv_estimate applied to both search routes | 2026-05-15 |
| 80 | Inline search — POST /properties/search + searchPropertiesInline — unsaved filter state executes without saving | 2026-05-15 |
| 81 | canSearch relaxed — selectedProfileId no longer required; 2 filters + county selection sufficient | 2026-05-15 |
| 82 | profiles.ts — toggleFavorite added | 2026-05-15 |
| 83 | End-to-end search verified — 23,087 Santa Rosa results, eff_yr_blt > 1945 + tot_lvg_area > 1,700 sqft | 2026-05-15 |
| 84 | Missing await db.commit() in routes/profiles.py — create_profile, clone_profile, update_profile, delete_profile, toggle_favorite | 2026-05-15 |
| 85 | Map pin rendering — Marker wired in ResultsPage, pageResults only, null coordinate guard, cursor pointer | 2026-05-23 |
| 86 | Dashboard Run button navigates directly to /results — bypasses Search page | 2026-05-15 |
| 87 | Dashboard Edit button added to ProfileRow — navigates to /search with profile pre-loaded | 2026-05-15 |
| 88 | Edit Filter back-navigation fixed — navStateConsumed ref removed, useEffect dependency changed to location.state | 2026-05-15 |
| 89 | ResultsPage TypeScript errors resolved — CSS module declaration, FilterState null assertion, unused Marker import removed | 2026-05-15 |
| 90 | DashboardPage TypeScript errors resolved — handleToggleFavorite moved inside component body, prev typed explicitly | 2026-05-15 |
| 93 | Marker click highlights corresponding table row, scrolls it into view, and recenters map via easeTo | 2026-05-23 |
| 94 | "See on map" — drawer locate button, onLocate callback, easeTo via MapRef, closes drawer and opens popup | 2026-05-23 |
| 96 | SearchPage unsaved filter state lost on Edit Filter — useNav condition broadened to trigger on filterState presence, not profileId only | 2026-05-24 |
| 97 | ResultsPage profile-based search ignores edited filterState — inline path now used whenever filterState is present in nav state, regardless of profileId | 2026-05-24 |
| 98 | Deployment workflow — frontend build consolidated into nginx multi-stage image; frontend service and frontend_dist named volume eliminated; frontend/Dockerfile deleted | 2026-05-24 |
| 99 | Root .dockerignore — removed frontend/ exclusion to allow nginx multi-stage build to access frontend source from repo root build context | 2026-05-24 |
| 100 | Santa Rosa CAMA scraper — migrate parcelview → parcelcard endpoint; host_database_url fix for host-side scripts | 2026-05-24 |
| 101 | Escambia CAMA scraper — instrument_type/qualification_code column mapping fix; full reset and restart via unattended wrapper | 2026-05-26 |
| 102 | Pagination stability fix — added ORDER BY county_fips, parcel_id to both search route DB fetches; added parcel_id tiebreaker to _build_page sort key. Resolves Escambia pagination returning identical records on every page change. | 2026-05-25 |
| 104 | Search architecture — Option C hybrid. Lightweight scoring fetch (5 columns) replaces full ORM load for all filtered rows. Full ORM hydration scoped to page slice only (25 rows). Both search routes unified through _execute_search. _build_page eliminated. County-scoped page hydration preserves item 78 fix. | 2026-05-25 |
| 107 | Column sort — sortable headers in ResultsPage, backend _sort_key for 9 fields, scored.sort() call, max_results cap moved post-sort | 2026-05-26 |
| 108 | Documentation overhaul — arv.md rewritten (qualification systems reconciled, C code resolved, bed_bath_source hierarchy defined); DECISIONS.md updated (ingest user-agnostic rule, ARV systems, search architecture debt, SalesComp/PropertyValueHistory notes); scrapers.md updated | 2026-05-26 |
| 109 | Parser overhaul — listing_matcher.py, lis_pendens_parser.py, foreclosure_parser.py, tax_deed_parser.py, zillow_parser.py: mqi_qualified removed, filter_profile_id removed, arv_source corrected to JV_FALLBACK, workflow_status corrected to NEW, datetime.utcnow() fixed, f-string JSON replaced with json.dumps(), _lookup_parcel() extended to return arv_estimate | 2026-05-26 |
| 110 | listing_events data fix — 6,011 lowercase workflow_status 'new' rows corrected to 'NEW' | 2026-05-26 |
| 111 | v0.20 migration — listing_events workflow_status CHECK constraint live and verified | 2026-05-26 |
| 112 | qualification_code 'C' resolved — confirmed "Qualified and Confirmed" by Santa Rosa County PA (Richard Brosnaham, 2026-05-26). arv.md and DECISIONS.md updated. | 2026-05-26 |
| 113 | v0.21 migration — arv_source column added to properties table | 2026-05-28 |
| 114 | arv_calculator.py refactor — three-pass comp engine (PSH primary, PSH wider, NAL spatial fallback), two-tier gate, county viability pre-flight. Santa Rosa first pass: 67,545 COMP / 52,955 JV_FALLBACK / 120,500 updated. | 2026-05-28 |
| 117 | Address sort — USPS-style street-name sort with nulls-last on both directions. _address_sort_key() in properties.py. | 2026-05-28 |
| 118 | Escambia CAMA — NOT_FOUND sentinel + cama_enriched_at stamp for permanent not-found parcels. Inter-request delay on not-found path. | 2026-05-28 |
| 119 | Persistent nav bar — AppNav component extracted. Brand, Dashboard, New Search, Sign Out accessible from all authenticated pages. | 2026-05-28 |
| 120 | ResultsPage filterState type annotation corrected to FilterState | null. Page-specific actions moved to sub-header below persistent nav. | 2026-05-28 |
| 121 | SearchPage Sort By options expanded to match all backend supported_sort_fields — address and tot_lvg_area added. | 2026-05-28 |
