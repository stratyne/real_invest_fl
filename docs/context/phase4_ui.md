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

## Planned Features

- Filter profile management (create, clone system profile, edit, delete)
- Ranked property list (sorted/filtered on pre-computed columns)
- Map view (MapLibre GL JS, PostGIS geometry)
- Outreach template generation
- One-click email send with Calendly/Google Calendar link
- Full outreach log
- Multi-user, multi-county, subscription-gated

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

- API routes sort and filter on pre-computed columns only
- Filter profile save/modify triggers background recompute of listing_events
  for that county_fips
- deal_score_version tracks algorithm version for auditability
- passed_filters, filter_rejection_reasons, deal_score computed at query time
- County access enforced via require_county_access dependency on every
  county-scoped route — not at the application layer
- Standardize require_county_access path-parameter pattern before
  endpoints proliferate

## Pre-flight Checklist

- [ ] seed_superuser.py run (item 11)
- [ ] seed_bundles.py run (item 12)
- [ ] require_county_access path-parameter pattern standardized
- [ ] Phase 4 route design documented before code is written
