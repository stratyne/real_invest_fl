# Project Penstock — AGENTS.md
# Source of truth for AI agent operation. Paste at every session open.
# Last updated: 2026-05-04

## Project Identity
- **Name:** Project Penstock
- **Repo:** stratyne/real_invest_fl (public — use raw URLs, login required for UI)
- **Local path:** D:\Chris\Documents\Stratyne\real_invest_fl
- **Python:** 3.13.5 | **Venv:** .venv | **Editor:** VSCodium 1.112.01907
- **DB container:** Docker — `real_invest_db`
  (localhost:5432, user penstock, db real_invest_fl)
- **DB verify:** `docker exec -it real_invest_db psql -U penstock -d real_invest_fl -c "<query>"`

## Non-Negotiable Rules
- **This is a real-world production project. Failures have real consequences. Do not assume in order to appease or speed up the process.**
- NEVER assume file contents, file paths, or schema details not explicitly provided.
- NEVER guess. If you need a file, ASK. If you need a path, ASK.
- NEVER reference or merge `stratyne/pensacola_invest_bot` — separate deliverable.
- NEVER apply filter criteria at ingest time. Filters are query-time only.
- NEVER use raw string SQL. All SQL in batch scripts uses `text()`.
- NEVER use `::jsonb` in `text()` statements. Use `CAST(:x AS jsonb)`.
- NEVER call `normalize_parcel_id()` in scrapers — use raw strip+uppercase only.
- NEVER overwrite a good DB value with None from a failed parse.
- NEVER make assumptions to appease or speed up the process.
- All design decisions documented before code is written.
- Checkpoint (STATE.md) updated at the end of every session.

## Commit Convention
Conventional Commits: `feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`

## DB Session Pattern
- Async (`settings.database_url`): ORM / FastAPI routes
- Sync (`settings.sync_database_url`): batch scripts, seed scripts, ingest

## Document Map
| Question | Document |
|---|---|
| Where are we? What's next? What's blocked? | `docs/STATE.md` |
| Why is it designed this way? Schema? Rules? | `docs/DECISIONS.md` |
| How does this specific subsystem work? | `docs/context/{topic}.md` |

## Session Open Protocol
1. Always paste `AGENTS.md` (this file).
2. Paste `docs/context/{topic}.md` for your work area (see map below).
3. Paste `STATE.md` only if discussing priorities or planning.
4. Paste `DECISIONS.md` only if a design question arises.

## Context File Map
| Work area | Paste this |
|---|---|
| ARV / deal scoring / comp engine | `context/arv.md` |
| CAMA ingest / scraping | `context/cama.md` |
| NAL / GIS ingest pipeline | `context/ingest.md` |
| Scrapers / listing sources | `context/scrapers.md` |
| Auth / users / seeds | `context/auth.md` |
| Phase 4 UI (FastAPI + React) | `context/phase4_ui.md` |
| Address normalization / matching | `context/scrapers.md` |
| Schema questions | `docs/DECISIONS.md` (Schema Reference section) |
