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

- [ ] seed_superuser.py run (item 11)
- [ ] seed_bundles.py run (item 12)
- [ ] require_county_access path-parameter pattern standardized
- [ ] Phase 4 route design documented before code is written
