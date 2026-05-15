# Project Penstock — context/phase4_ui.md
# Paste this alongside AGENTS.md when working on Phase 4 UI.
# Last updated: 2026-05-14

## Status

ACTIVE — Phase 4 in progress. See STATE.md for item status.

## Tech Stack

| Layer | Technology |
|---|---|
| API framework | FastAPI + Uvicorn |
| Frontend | React (Vite) |
| Map | MapLibre GL JS |
| Auth | JWT HS256 (PyJWT) — already implemented |
| DB (async) | SQLAlchemy 2.x async + asyncpg |

## User Flow (process sequence — applies to all users regardless of criteria)

1. Orient — user logs in and lands on the dashboard. Sees their saved
   filter profiles ordered by favorite → last run → run count, plus
   outreach pipeline status (drafts pending, sent this week, responses
   received). No filter profile is required to reach this view. No
   inventory counts are shown. A user who has never run a search sees an
   empty profile list with a prompt to select or create one.
2. Select profile — user picks a saved profile from the dashboard to
   run, or navigates to create or edit a profile. The most recently run
   profile is at the top of the list unless a favorite is pinned above it.
   County is implied by the profile's county_fips — there is no separate
   county selection step on the dashboard.
3. Define — if creating or editing, user configures filter parameters
   for their selected county. Filter profile save and execute are distinct
   operations. Save writes to filter_profiles only. Execute triggers the
   live search query.
4. Execute — user hits Search. FastAPI builds a live query against
   properties and listing_events using filter criteria as WHERE clauses
   and deal score weights for ORDER BY. ARV pulled from
   listing_events.arv_estimate (comp-based where available, jv fallback).
   Results returned ranked by deal score. user_profile_prefs upserted
   after successful fetch — last_searched_at, last_result_count, and
   run_count updated.
5. Review — user sees ranked property list with key metrics. Map view
   available via MapLibre GL JS.
6. Select — user selects one or more properties to act on.
7. Generate — system auto-generates outreach message from template,
   with calendar booking link embedded.
8. Approve and Send — user reviews generated message, clicks to send.
   One-click trigger. Email sent via SendGrid/Gmail SMTP.
9. Log — sent message, timestamp, recipient, and property recorded in
   outreach_log. Responses logged when received.
10. Recurring — daily scheduler (item 20) runs the pipeline on cadence,
    keeping listing_events current so search results reflect latest signals.

## Planned Features

- Inventory dashboard — profile activity list (favorites + last run +
  run count) and outreach pipeline status. No inventory counts. No raw
  signals outside search context.
- Favorite toggle on any profile (system or user-owned) — per-user
  bookmark, pure UI, no functional weight.
- Ranked property list (query-time, sorted by deal score, requires
  filter profile)
- Filter profile management (create, clone system profile, edit, delete)
- Map view (MapLibre GL JS, PostGIS geometry)
- Outreach template generation (triggered by user selection)
- One-click email send with calendar booking link
- Full outreach log with response tracking
- Multi-user, multi-county, subscription-gated
- On-demand search (user-initiated) and recurring cadence (scheduler)
  both supported

## API Route Files

real_invest_fl/api/routes/
  approvals.py
  config.py
  counties.py
  dashboard.py
  ingest.py
  listings.py
  outreach.py       -- implemented (items 39-41)
  properties.py
  profiles.py

## Key Design Constraints

- The dashboard is a user-activity view. It never surfaces raw inventory
  counts or listing_events rows. Signals have no meaning outside a search
  execution and do not appear on the dashboard under any circumstances.
- Search execution is query-time only. FastAPI builds a SQL query against
  properties and listing_events using filter profile criteria as WHERE
  clauses and deal score weights for ORDER BY. No pre-computation, no cache.
- listing_events is a pure event log. It carries no scoring columns.
  Scoring output lives in listing_scores.
- listing_scores is written only when a user acts on a result (selects
  a property and initiates outreach). It is an audit record, not a search
  index.
- Filter profile save and execute are distinct operations — save writes to
  filter_profiles only, execute triggers the live search query.
- County access enforced via county_access() dependency on every
  county-scoped route — not at the application layer.
- Phase 4 route design must be documented before code is written.
- ARV displayed in results is comp-based where sufficient comps exist,
  jv fallback otherwise. arv_source surfaced in all result views.
  Do not treat COMP and JV_FALLBACK as equivalent in UI display.
- user_profile_prefs is upserted by the search route on every successful
  execution. It is the authoritative source for dashboard profile ordering.
  It is never written by any route except search and the favorite toggle.

## Pre-flight Checklist

- [x] seed_superuser.py run (item 11)
- [x] seed_bundles.py run (item 12)
- [x] require_county_access path-parameter pattern standardized
- [x] Phase 4 route design documented before code is written
- [x] v0.17 migration live — outreach_templates, skip_trace_cache, outreach_log, users.calendar_link
- [x] v0.18 migration — user_profile_prefs

## Route Design (locked 2026-05-04, updated 2026-05-14)

All routes documented here before implementation. No route is written
until it appears in this table. County-scoped routes always use
Depends(county_access()) — never the explicit await pattern.

### Conventions

- County-scoped routes: prefix /{county_fips}/
- Auth dependency: county_fips: str = Depends(county_access())
- Routes needing the user object declare it separately:
  current_user: User = Depends(get_current_user)
- All responses use Pydantic response models — no ORM objects returned raw.
- HTTP methods follow REST strictly:
  GET = read, POST = create, PATCH = partial update, DELETE = remove.
- 404 returned when a resource does not exist within the user's
  authorized scope.
- 403 returned by county_access() before the route body executes —
  routes never manually re-check county access.

### Route Table

#### Auth — /auth (no county scope)
| Method | Path | Handler | Description |
|---|---|---|---|
| POST | /auth/token | login | OAuth2 password flow. Returns JWT. Already implemented. |
| GET | /auth/me | get_me | Returns current user profile. Already implemented. |

#### Counties — /counties (no county scope)
| Method | Path | Handler | Description |
|---|---|---|---|
| GET | /counties | list_counties | Returns all active counties the current user has access to. Joins user_county_access to counties WHERE active = TRUE. Superusers see all active counties. |

#### Filter Profiles — /profiles (no county scope)
| Method | Path | Handler | Description |
|---|---|---|---|
| GET | /profiles | list_profiles | Returns all system profiles + current user's own profiles visible to the user. Each profile includes the user's user_profile_prefs row if one exists (is_favorite, last_searched_at, last_result_count, run_count). Access filtered internally via _get_accessible_fips() — no county path parameter. |
| POST | /profiles | create_profile | Creates a new user-owned profile. user_id set server-side. county_fips is list[str] in request body — user must have access to all counties listed. |
| POST | /profiles/{profile_id}/clone | clone_profile | Clones any visible profile into a new user-owned profile. New profile name required in request body. Optional county_fips override accepted as list[str]. |
| PATCH | /profiles/{profile_id} | update_profile | Updates a user-owned profile. Returns 403 if system profile or belongs to another user. |
| DELETE | /profiles/{profile_id} | delete_profile | Deletes a user-owned profile. Returns 403 if system profile or belongs to another user. Superusers may delete any non-system profile. |
| PATCH | /profiles/{profile_id}/favorite | toggle_favorite | Toggles is_favorite on user_profile_prefs for (current_user.id, profile_id). Creates row if not exists. No request body. Returns { "is_favorite": bool }. |

#### Properties — /properties (no county scope) and /{county_fips}/properties/{parcel_id}
| Method | Path | Handler | Description |
|---|---|---|---|
| GET | /properties | search_properties | Core search route. Accepts filter_profile_id as query param. Loads profile, builds WHERE clauses from filter_criteria across all counties in profile.county_fips, computes deal score at query time, returns results ranked by deal score. Upserts user_profile_prefs after successful fetch. |
| POST | /properties/search | search_properties_inline | Inline search — accepts full filter payload in request body (county_fips list, filter_criteria, deal_score_weights, ARV engine params). No profile written. Access validated against county_fips array. Behaviour otherwise identical to search_properties. Used when executing unsaved filter state. |
| GET | /{county_fips}/properties/{parcel_id} | get_property | Returns full property detail for a single parcel. Includes latest listing_event if present. county_fips path parameter enforced via county_access() dependency. |

#### Listings — /{county_fips}/listings
| Method | Path | Handler | Description |
|---|---|---|---|
| GET | /{county_fips}/listings | list_listings | Returns listing_events for the county, optionally filtered by workflow_status, signal_tier, signal_type, listing_type. |
| GET | /{county_fips}/listings/{listing_id} | get_listing | Returns a single listing_event by id. |
| PATCH | /{county_fips}/listings/{listing_id}/status | update_listing_status | Updates workflow_status on a listing_event. Valid transitions enforced server-side. |

#### Outreach — /{county_fips}/outreach
| Method | Path | Handler | Description |
|---|---|---|---|
| POST | /{county_fips}/outreach/generate | generate_outreach | Accepts parcel_id + listing_event_id + filter_profile_id + template_id + optional force=true. Validates listing_event belongs to county_fips and parcel_id. Checks for existing listing_scores row — returns warning payload if found and force not set. Writes listing_scores audit row. Snapshots recipient data and skip_trace_cache result. Renders Jinja2 template. Writes DRAFT outreach_log row. Returns draft — does not send. |
| POST | /{county_fips}/outreach/send | send_outreach | Accepts outreach_log_id. Validates log row belongs to current_user and status = DRAFT. Guards message_body NOT NULL. Sends via SendGrid. Updates status = SENT, sent_at = now(). On failure: status = FAILED, send_error populated. |
| GET | /{county_fips}/outreach | list_outreach | Returns outreach_log rows for the county scoped to current_user. Superusers see only their own rows. |
| POST | /{county_fips}/outreach/skip_trace | skip_trace | Accepts parcel_id. Returns cached skip_trace_cache row if present and not expired. Returns 501 when BATCHDATA_API_KEY not configured. |

#### Dashboard — /dashboard (no county scope)
| Method | Path | Handler | Description |
|---|---|---|---|
| GET | /dashboard | get_dashboard | Returns two payloads for the current user. (1) Profile activity list: user_profile_prefs joined to filter_profiles, ordered by is_favorite DESC, last_searched_at DESC NULLS LAST, run_count DESC. Each entry carries profile_id, profile_name, county_fips, is_system, is_favorite, last_searched_at, last_result_count, run_count. (2) Outreach pipeline status: drafts_pending, sent_this_week, responses_received. No inventory counts. No raw listing_events. No filter profile applied. |

#### Ingest — /ingest (superuser only, no county scope)
| Method | Path | Handler | Description |
|---|---|---|---|
| GET | /ingest/status | get_ingest_status | Returns data_source_status rows for all counties. Superuser only — raises 403 for non-superusers. |

#### Config — /config (superuser only, no county scope)
| Method | Path | Handler | Description |
|---|---|---|---|
| GET | /config/counties | list_all_counties | Returns all counties including inactive. Superuser only. |
| PATCH | /config/counties/{county_fips} | update_county | Updates county metadata (active flag, file paths). Superuser only. |

### Route Files → Route Mapping

| File | Routes |
|---|---|
| routes/auth.py | /auth/token, /auth/me — already implemented |
| routes/counties.py | /counties |
| routes/config.py | /config/counties (list + update) |
| routes/properties.py | /properties (search + inline search), /{county_fips}/properties/{parcel_id} (detail) |
| routes/listings.py | /{county_fips}/listings (list + detail + status update) |
| routes/outreach.py | /{county_fips}/outreach (generate + send + list + skip_trace) |
| routes/profiles.py | /profiles (list + create + clone + update + delete + favorite toggle) |
| routes/dashboard.py | /dashboard |
| routes/ingest.py | /ingest/status |
| routes/approvals.py | Reserved — workflow approval step, Phase 4 tail |

### Dashboard + Profile Prefs Implementation Order (locked 2026-05-14)

1. [x] DECISIONS.md + phase4_ui.md + schema.md updated (item 51)
2. [x] v0.18 migration — user_profile_prefs
3. [x] ORM model — UserProfilePrefs
4. [x] routes/dashboard.py — get_dashboard
5. [x] routes/profiles.py — toggle_favorite added
6. [ ] routes/properties.py — upsert added to search_properties and search_properties_inline
7. [x] DashboardPage.tsx — rewrite to profile activity + pipeline status

### Outreach UI Requirements (locked 2026-05-05)

- Warn user at generate time if current_user.calendar_link is NULL and
  the selected template is the system EMAIL template.
- Surface arv_source distinction (COMP vs JV_FALLBACK) in all property
  result views — do not treat as equivalent.
- LETTER output: React react-to-print + window.print(). No server-side PDF.

### Deferred from Phase 4 Scaffold

- Zestimate fetch endpoint (item 21) — RapidAPI wrapper not yet built
- Google Sheets export (item 22) — output pipeline Phase 2 tail
- Email response tracking (item 23) — inbound webhook, Phase 4 tail
- User management endpoints — registration, password reset, admin user CRUD
- Approval workflow (approvals.py) — deferred until outreach flow is live
- Skip-trace live integration (item 44) — schema scaffold in place
- Map pins — coordinate data not on PropertySearchResult (item 49)
- Server-side pagination — currently client-side (item 50), Phase 4 tail
- Cross-county profile search beyond user's granted counties — access gating enforced per county
