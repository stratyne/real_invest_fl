# Project Penstock — context/phase4_ui.md
# Paste this alongside AGENTS.md when working on Phase 4 UI.
# Last updated: 2026-05-04
# NOTE: Phase 4 has not started. This file is a pre-flight scaffold.
# Update this file as decisions are made during Phase 4 development.

## Status

NEXT — blocked on items 11 and 12 (seed scripts). See auth.md.

## Tech Stack

| Layer | Technology |
|---|---|
| API framework | FastAPI + Uvicorn |
| Frontend | React (Vite) |
| Map | MapLibre GL JS |
| Auth | JWT HS256 (PyJWT) — already implemented |
| DB (async) | SQLAlchemy 2.x async + asyncpg |

## User Flow (process sequence — applies to all users regardless of criteria)

1. **Define** — user creates or selects a saved filter profile for their county.
2. **Execute** — user hits Search. FastAPI runs live query against `properties`
   and `listing_events`. ARV pulled from listing_events.arv_estimate
   (comp-based where available, jv fallback). Results returned ranked by
   deal score.
3. **Review** — user sees ranked property list with key metrics. Map view
   available via MapLibre GL JS.
4. **Select** — user selects one or more properties to act on.
5. **Generate** — system auto-generates outreach message from template,
   with Calendly/Google Calendar booking link embedded.
6. **Approve and Send** — user reviews generated message, clicks to send.
   One-click trigger. Email sent via SendGrid/Gmail SMTP.
7. **Log** — sent message, timestamp, recipient, and property recorded in
   `outreach_log`. Responses logged when received.
8. **Recurring** — daily scheduler (item 20) runs the pipeline on cadence,
   keeping `listing_events` current so search results reflect latest signals.

## Planned Features

- Filter profile management (create, clone system profile, edit, delete)
- Ranked property list (query-time, sorted by deal score)
- Map view (MapLibre GL JS, PostGIS geometry)
- Outreach template generation (triggered by user selection at step 4)
- One-click email send with Calendly/Google Calendar booking link
- Full outreach log with response tracking
- Multi-user, multi-county, subscription-gated
- On-demand search (user-initiated) and recurring cadence (scheduler) both supported

## API Route Stubs (currently empty)

real_invest_fl/api/routes/
  approvals.py
  config.py
  counties.py
  dashboard.py
  ingest.py
  listings.py
  outreach.py
  properties.py

## Key Design Constraints

- Search execution is query-time only. FastAPI builds a SQL query against
  `properties` and `listing_events` using filter profile criteria as WHERE
  clauses and deal score weights for ORDER BY. No pre-computation, no cache.
- `listing_events` is a pure event log. It carries no scoring columns.
  Scoring output lives in `listing_scores`.
- `listing_scores` is written only when a user acts on a result (selects a
  property and initiates outreach). It is an audit record, not a search index.
- Filter profile save and execute are distinct operations — save writes to
  `filter_profiles` only, execute triggers the live search query.
- County access enforced via require_county_access dependency on every
  county-scoped route — not at the application layer.
- Standardize require_county_access path-parameter pattern before
  endpoints proliferate.
- Phase 4 route design must be documented before code is written.
- ARV displayed in results is comp-based (parcel_sale_history qual_cd='01')
  where sufficient comps exist, jv fallback otherwise. arv_source column
  indicates which was used. Do not treat jv and comp-based ARV as equivalent
  in UI display — surface the distinction to the user.

## Pre-flight Checklist

- [✅] seed_superuser.py run (item 11)
- [✅] seed_bundles.py run (item 12)
- [✅] require_county_access path-parameter pattern standardized
- [✅] Phase 4 route design documented before code is written

## Route Design (locked 2026-05-04)

All routes documented here before implementation. No route is written
until it appears in this table. County-scoped routes always use
`Depends(county_access())` — never the explicit await pattern.

### Conventions

- County-scoped routes: prefix `/{county_fips}/`
- Auth dependency: `county_fips: str = Depends(county_access())`
- Routes needing the user object declare it separately:
  `current_user: User = Depends(get_current_user)`
- All responses use Pydantic response models — no ORM objects returned raw.
- HTTP methods follow REST strictly:
  GET = read, POST = create, PATCH = partial update, DELETE = remove.
- 404 returned when a resource does not exist within the user's authorized scope.
- 403 returned by county_access() before the route body executes — routes
  never manually re-check county access.

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

#### Filter Profiles — /{county_fips}/profiles
| Method | Path | Handler | Description |
|---|---|---|---|
| GET | /{county_fips}/profiles | list_profiles | Returns all system profiles + current user's own profiles for the county. System profiles: user_id IS NULL. User profiles: user_id = current_user.id. |
| POST | /{county_fips}/profiles | create_profile | Creates a new user-owned profile. user_id set server-side to current_user.id — never accepted from request body. |
| POST | /{county_fips}/profiles/{profile_id}/clone | clone_profile | Clones any visible profile (system or own) into a new user-owned profile. New profile name required in request body. |
| PATCH | /{county_fips}/profiles/{profile_id} | update_profile | Updates a user-owned profile. Returns 403 if profile belongs to another user. Returns 403 if profile is a system profile (user_id IS NULL). |
| DELETE | /{county_fips}/profiles/{profile_id} | delete_profile | Deletes a user-owned profile. Returns 403 if system profile. Returns 403 if profile belongs to another user. Superusers may delete any non-system profile. |

#### Properties — /{county_fips}/properties
| Method | Path | Handler | Description |
|---|---|---|---|
| GET | /{county_fips}/properties | search_properties | Core search route. Accepts filter_profile_id as query param. Loads the profile, builds WHERE clauses from filter_criteria, computes deal score at query time, returns results ranked by deal score. ARV sourced from listing_events.arv_estimate; arv_source surfaced in response. jv fallback clearly distinguished from COMP in response payload. |
| GET | /{county_fips}/properties/{parcel_id} | get_property | Returns full property detail for a single parcel. Includes latest listing_event if present. |

#### Listings — /{county_fips}/listings
| Method | Path | Handler | Description |
|---|---|---|---|
| GET | /{county_fips}/listings | list_listings | Returns listing_events for the county, optionally filtered by workflow_status, signal_tier, signal_type, listing_type. |
| GET | /{county_fips}/listings/{listing_id} | get_listing | Returns a single listing_event by id. |
| PATCH | /{county_fips}/listings/{listing_id}/status | update_listing_status | Updates workflow_status on a listing_event. Valid transitions enforced server-side. |

#### Outreach — /{county_fips}/outreach
| Method | Path | Handler | Description |
|---|---|---|---|
| POST | /{county_fips}/outreach/generate | generate_outreach | Accepts parcel_id + listing_event_id + filter_profile_id. Generates outreach message from template. Writes listing_scores row (audit record). Returns draft message — does not send. |
| POST | /{county_fips}/outreach/send | send_outreach | Accepts outreach_log_id. Sends the approved message via SendGrid/SMTP. Updates outreach_log with sent_at timestamp. |
| GET | /{county_fips}/outreach | list_outreach | Returns outreach_log rows for the county, scoped to current user. |

#### Dashboard — /dashboard (no county scope)
| Method | Path | Handler | Description |
|---|---|---|---|
| GET | /dashboard | get_dashboard | Returns cross-county summary for the current user: active listings count, recent signals, outreach activity. Scoped to counties the user has access to. |

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
| routes/properties.py | /{county_fips}/properties (search + detail) |
| routes/listings.py | /{county_fips}/listings (list + detail + status update) |
| routes/outreach.py | /{county_fips}/outreach (generate + send + list) |
| routes/dashboard.py | /dashboard |
| routes/ingest.py | /ingest/status |
| routes/approvals.py | Reserved — workflow approval step, Phase 4 tail |

### Deferred from Initial Phase 4 Scaffold
- Zestimate fetch endpoint (item 21) — RapidAPI wrapper not yet built
- Google Sheets export (item 22) — output pipeline Phase 2 tail
- Email response tracking (item 23) — inbound webhook, Phase 4 tail
- User management endpoints — registration, password reset, admin user CRUD
- Approval workflow (approvals.py) — deferred until outreach flow is live
