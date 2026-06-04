# Project Penstock - AGENTS.md
# Source of truth for AI agent operation. Paste at every session open.
# Last updated: 2026-06-04

## Project Identity
- **Name:** Project Penstock
- **Repo:** stratyne/real_invest_fl (public - use raw URLs, login required for UI)
- **Local path:** D:\Chris\Documents\Stratyne\real_invest_fl
- **Python:** 3.13.5 | **Venv:** .venv | **Editor:** VSCodium 1.112.01907
- **DB container:** Docker - `real_invest_db`
  (localhost:5432, user penstock, db real_invest_fl)
- **DB verify:** `docker exec -it real_invest_db psql -U penstock -d real_invest_fl -c "<query>"`

## Non-Negotiable Rules
- **This is a real-world production project. Failures have real consequences. Do not assume in order to appease or speed up the process.**
- NEVER assume file contents, file paths, or schema details not explicitly provided.
- NEVER guess. If you need a file, ASK. If you need a path, ASK.
- NEVER reference or merge `stratyne/pensacola_invest_bot` - separate deliverable.
- NEVER apply filter criteria at ingest time. Filters are query-time only.
- NEVER use non-ASCII characters anywhere in code, comments, docstrings, or
  print statements. Use only plain ASCII. This project runs on Windows
  terminals using cp1252 encoding.
- NEVER use raw string SQL. All SQL in batch scripts uses `text()`.
- NEVER use `::jsonb` in `text()` statements. Use `CAST(:x AS jsonb)`.
- NEVER call `normalize_parcel_id()` in scrapers - use raw strip+uppercase only.
- NEVER overwrite a good DB value with None from a failed parse.
- NEVER make assumptions to appease or speed up the process.
- NEVER present bare SQL queries. Always deliver queries as complete, copy-pasteable
  PowerShell commands using the DB verify pattern defined in Project Identity.
- All design decisions documented before code is written.
- Checkpoint (STATE.md) updated at the end of every session.

## Pre-Response Checklist
Before producing any response, the agent must verify:

- [ ] Does this response require the user to perform any manual formatting,
      wrapping, or templating step before it is usable?
- [ ] Have I declared anything impossible without exhausting all available
      tools, data, and computable approaches?
- [ ] Am I applying a specific fix to what is actually a broader problem?
      If so, identify the general principle and address that instead.
- [ ] Have I reasoned through whether a higher-level approach exists before
      proposing this solution?
- [ ] Have I explicitly connected this task to the active phase and active
      items in STATE.md?
- [ ] Does this task conflict with or duplicate an existing active item?
      If so, flag it before proceeding.
- [ ] Does this response violate any Non-Negotiable Rule?

If the answer to any item is YES, correct the response before sending it.

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
5. Before any work begins, the agent must produce the following confirmation:

   "I have read AGENTS.md in full. I confirm the following behavioral commitments:
   1. I will never declare something impossible without exhausting all available
      tools, data, and computable approaches.
   2. I will never present output that requires the user to perform a manual
      formatting or wrapping step. All output is delivered ready to use.
   3. I will never apply a specific fix to a broader problem. When a mistake or
      gap is identified, I will identify the general principle it violates and
      address that principle.
   4. I will never propose a solution without first reasoning through whether a
      higher-level approach exists. I will not solve the instance if the pattern
      is the real problem.
   5. I will never lose the thread of the larger project goal. Before beginning
      any task I will explicitly state how it connects to the active phase and
      active items. I will flag any task that appears to conflict with or be
      redundant to an existing active item.
   6. I will apply all Non-Negotiable Rules without exception. I will not treat
      them as advisory. If I am uncertain whether a rule applies, I will ask
      before proceeding."

   The agent may not proceed with any task until this confirmation is produced.

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
| Schema questions / migrations / ORM models | `context/schema.md` |

