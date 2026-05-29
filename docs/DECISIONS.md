# Project Penstock — DECISIONS.md
# Authoritative record of current architectural decisions.
# Always current — edit in place when a decision changes.
# The git commit message is the audit trail, not this file.
# Last updated: 2026-05-28

---

## Strategic Vision

Penstock is a multi-user, inventory-first real estate investment property
discovery and scoring platform for Florida. It ingests the complete public
property tax roll for every Florida county — every parcel, every use code,
no filtering at ingest time — and stores it as a clean, queryable inventory.
Users build and manage their own filter profiles that run against that shared
inventory at query time.

Long-term: statewide platform covering all 67 FL counties, competing
commercially with PropStream. Escambia County is the proof-of-concept.

The original SOW (single investor, single county, hardcoded criteria,
Google Sheet output) is ONE example of what a single user's filter profile
produces. It is not the architecture. It is a test case.

---

## Data Architecture

- ARV uses a comp-based model drawing from parcel_sale_history filtered by
  PA-level qualification codes. jv is retained as fallback ARV proxy when
  insufficient comps exist. Full detail in context/arv.md.
- Signal model is primary. Traditional listing model is a parallel track.
- listing_events is the unified output table for all signal and listing sources.
- Multi-year SDF is a future enhancement to comp pool depth, not a dependency.
  NAV deferred until deal scoring is an approved deliverable.
- The platform serves infinite users with infinite use cases.

---

## Ingest Pipeline

- Filters are query-time only. The ingest pipeline NEVER applies filter
  criteria. Every parcel from every county NAL goes into properties
  regardless of use code, size, value, or any other criterion.
- Ingest is user-agnostic. No parser, scraper, or ingest script ever
  references a user, a filter profile, or any user-owned construct.
  Events are recorded as they exist in the real world. Whether an event
  is relevant to a specific user is answered exclusively at query time.
  Practically: filter_profile_id is never written by any parser or
  scraper. _get_filter_profile_id() does not belong in any parser or
  scraper. mqi_qualified is never referenced by any parser or scraper.
  Any future user_id, tenant_id, or similar user-owned construct is
  subject to the same rule without exception.
- All ingest scripts resolve file paths programmatically from the county
  registry using the canonical folder pattern. File discovery uses globs,
  never hardcoded filenames. Full detail in context/ingest.md.
- dor_uc normalized to zero-padded three digits at ingest via
  nal_mapper.py _dor_uc() helper.
- mqi_qualified, mqi_rejection_reasons, mqi_qualified_at are POC artifacts.
  All rows carry mqi_qualified = false as a neutral placeholder. These
  columns will be removed in a pending migration once the Phase 4
  query-time filter is live.

---

## Database / ORM

- Async (settings.database_url): ORM / FastAPI routes.
- Sync (settings.sync_database_url): batch scripts, seed scripts, ingest.
- All SQL in batch scripts uses text() — never raw string SQL.
- CAST(:x AS jsonb) — never ::jsonb in text() statements.

---

## Parcel ID Normalization

- Strip non-alphanumeric, uppercase, NO zero-padding.
- properties.parcel_id stored as 16 chars.
- normalize_parcel_id() in parcel_id.py zero-pads to 18 — do NOT call it
  in scrapers. Use raw strip+uppercase only in all scraper code.

---

## Street Address Normalization

normalize_street_address() in real_invest_fl/utils/text.py is the single
shared normalizer for all scrapers and listing_matcher. Three-level address
matching fallback is implemented in listing_matcher.py. Full detail in
context/scrapers.md.

---

## CAMA Ingest Framework

Each county property appraiser has a different website, URL pattern, and
HTML structure. No shared scraper is possible. County modules are added
under real_invest_fl/ingest/cama/. base.py provides the shared framework
with no county-specific logic and no hardcoded defaults. Full detail in
context/cama.md.

---

## parcel_sale_history Table

- Stores full ownership chain per parcel from county PA scrape.
- Distinct from a future SDF-sourced sales comp table.
- Unique constraint: uq_psh_county_parcel_sale on
  (county_fips, parcel_id, sale_date, grantor, grantee).
- grantor/grantee NOT NULL DEFAULT '' — empty string used in place of NULL
  to ensure the unique constraint fires correctly on missing names.

### Known Limitation — Unique Constraint Edge Case

The unique constraint includes grantor and grantee. If a parcel has two
distinct sales on the same date with no grantor/grantee available (both
stored as empty string), the constraint will incorrectly deduplicate them
into one row. This is an accepted edge case. It will silently swallow
the second row on re-scrape. Documented here as a known limitation —
no action required unless duplicate suppression becomes a reported problem.

### Column Design (three distinct fields — do not conflate)

- instrument_type VARCHAR(10): deed instrument type. Values: WD (Warranty
  Deed), QD (Quit Claim Deed), CT (Court/Certificate), SW (Sheriff's
  Warrant), TD (Tax Deed), PR (Personal Representative), PB (Probate),
  LD (Lady Bird Deed), DD (Dissolution Deed), FJ (Final Judgment), and
  others. Source-dependent — not all counties surface this field.
  NULL where unavailable — do not substitute a default value.
- qualification_code VARCHAR(5): PA-level arms-length qualification flag.
  Confirmed values: Q = Qualified (arms-length), U = Unqualified,
  V = Vacant land, C = Qualified and Confirmed (Santa Rosa PA-local value,
  confirmed 2026-05-26 by Richard Brosnaham, Administrative Coordinator,
  Santa Rosa County PA. Contact: 850.983.1880. Equal or higher confidence
  than Q for comp selection.)
- sale_type VARCHAR(5): improved/vacant classification of the parcel at
  time of sale. Values: I = Improved, V = Vacant. Sourced from Santa Rosa
  parcelcard. Escambia parcelcard does not surface this field.

### County-Specific Scraper Mapping (verified 2026-05-26)

| County          | instrument_type                      | qualification_code | sale_type |
|-----------------|--------------------------------------|--------------------|-----------|
| Escambia (12033)| NULL — parcelcard does not surface   | Q/U where present  | NULL      |
| Santa Rosa (12113)| NULL — parcelcard does not surface | Q/U/C/V            | I/V       |

Note: The Escambia column mapping bug (item 101, completed 2026-05-26)
wrote instrument type values into sale_type and never populated
qualification_code. All affected rows were deleted. The run was restarted
with the corrected scraper. All current Escambia rows are clean.

### Arms-Length Filter Logic for ARV Engine (item 17)

Because neither Escambia nor Santa Rosa surfaces instrument_type on their
parcelcard, the practical arms-length filter for both counties is:

Primary comp pool (highest confidence):
  qualification_code IN ('Q', 'C') AND sale_price >= 10000

Note: 'C' means "Qualified and Confirmed" per Santa Rosa County PA
(confirmed 2026-05-26, Richard Brosnaham, Administrative Coordinator,
850.983.1880). Equal or higher confidence than 'Q'. Escambia does not
produce 'C' values — the filter is harmless for Escambia and correct
for Santa Rosa.

Wider comp pool (acceptable when primary is insufficient):
  qualification_code IN ('Q', 'C', 'U') AND sale_price >= 10000

When instrument_type IS NOT NULL (future counties that surface it):
  (instrument_type = 'WD' OR instrument_type IS NULL)
  AND qualification_code IN ('Q', 'C')
  AND sale_price >= 10000

Do not apply county-specific branching in the ARV engine — the filter
is identical across counties. The instrument_type IS NULL condition
handles counties that do not surface the field without special-casing.

Minimum price filter: sale_price >= 10000 (excludes nominal consideration
deeds — 555 WD sales between $1-$499 confirmed in Escambia data as
non-arms-length transfers).

---

## Scraping and Robots Policy

Tier 1 government sources use file-drop parsers — robots.txt blocks live
scraping. public.escambiaclerk.com permits generic crawlers but blocks
ClaudeBot by name and sits behind Cloudflare — Playwright required. Full
per-source detail in context/scrapers.md.

---

## Beds / Baths

- Populated opportunistically on parcel match from any listing source.
- bed_bath_source tracks provenance.
- Confidence hierarchy (highest to lowest):
    1. cama — PA parcelcard, most authoritative
    2. county_clerk — direct county government. Current clerk sources carry
       no beds/baths (legal event records only). Reserved for future county
       sources that surface building characteristics.
    3. zillow_staging / auction_com — equal confidence, third-party sourced
    4. manual — lowest, human-entered, no current write workflow
- Never overwrite an existing value with a lower-confidence source.
- If incoming source confidence equals existing, overwrite (fresher data
  from same source is acceptable).
- auction_com sentinel: total_bedrooms=0 / total_bathrooms=0 are
  missing-data sentinels — treat as None, never write to DB.
- Phase 3 sources (Landvoice, REDX, PropStream): slot at
  zillow_staging/auction_com level until data quality is evaluated.
- Logic lives in the parser layer. Not yet implemented — tracked as item 116.
- Full detail in context/arv.md and context/scrapers.md.

---

## ARV Comp Engine

Primary source is parcel_sale_history joined to properties, filtered by
PA-level qualification codes. Three-pass strategy: Pass 1 (PSH primary
pool, Q/C), Pass 2 (PSH wider pool, Q/C/U), Pass 3 (NAL spatial fallback,
qual_cd1 = '01'). jv is the floor when all passes yield insufficient comps.
arv_source values: COMP, NAL_COMP, JV_FALLBACK, ZESTIMATE, MANUAL.
NAL_COMP: Pass 3 NAL spatial fallback — comp calculation performed
using neighboring parcels' NAL-embedded sale_prc1. Lower confidence
than COMP (parcel_sale_history). Higher confidence than JV_FALLBACK
(raw jv substitution). Surface distinction in all UI views.
Full detail in context/arv.md.

## ARV Calculator Refactor (item 17) — 2026-05-28

All design decisions documented in context/arv.md.

---

## SalesComp ORM Model and sales_comps Table

Created in v0.2 as a forward placeholder for FL DOR SDF data (item 25).
Has no ingest pipeline and no ORM relationship on Property.
Contains no data. Do not use for ARV calculations — parcel_sale_history
is the comp source. Will remain as a placeholder until item 25 is
prioritized. Do not confuse with parcel_sale_history.

---

## PropertyValueHistory ORM Model

Real model, real table (created v0.2). Append-only annual value log.
Populated by the annual NAL refresh pipeline (item 28, Phase 3).
Contains no data until Phase 3 begins. Not a POC artifact.

---

## Signal Tiers

Signal tier reflects delivery source, not underlying event type. A
foreclosure on Zillow is Tier 3. The same event from Escambia Clerk
is Tier 1.

---

## Subscription and Access Model

- County is the fundamental unit of access control and monetization.
- Subscription tiers: single county, regional bundle, statewide, enterprise.
- First bundle: Pensacola Metro = Escambia (12033) + Santa Rosa (12113).
- User-county authorization: user_county_access join table.
- County access enforced via single reusable FastAPI dependency — not at
  the application layer.
- Multi-user from day one. No single-admin stub acceptable.

---

## Filter Profile Model

- Profiles scoped to county_fips.
- System profiles: user_id = NULL, visible to all authorized users,
  not editable or deletable by regular users.
- Users clone a system profile to create a private editable copy.
  "Save as my profile" is a first-class UI action.
- User profiles: user_id = owner, private, fully editable.
- Uniqueness enforced via two partial unique indexes:
  - System profiles: unique on (profile_name) WHERE user_id IS NULL
  - User profiles: unique on (user_id, profile_name) WHERE user_id IS NOT NULL
  - county_fips is a VARCHAR(5)[] array column — it cannot participate in a
    PostgreSQL unique index and is not part of either uniqueness constraint.
    Uniqueness is enforced on name alone within each ownership scope.
- Cross-county profiles deferred to Phase 3+. Single-county-per-route
  is an explicit architectural choice tied to the subscription model.

---

## Scoring and Filter Enforcement Model

- Search and filter execution is query-time only. FastAPI builds a SQL
  query against properties and listing_events using filter profile criteria
  as WHERE clauses and deal score weights as ORDER BY. No pre-computation.
  No background recompute job.
- passed_filters, filter_rejection_reasons, and deal_score are NOT stored
  on listing_events. They are computed at query time and returned in the
  response.
- listing_scores captures scoring output only when a user acts on a result
  (selects a property and initiates outreach). It is an audit record of
  the score at the moment of user action — not a search cache and not a
  pre-computed index.
- The score visible in search results and the score recorded in
  listing_scores at outreach-initiation time may differ if
  parcel_sale_history has grown between the two events. This is
  intentional — listing_scores is a point-in-time snapshot at the moment
  of user action, not a replay of the search result.
- Filter profile save and execute are two distinct operations:
  - Save: writes filter_criteria to filter_profiles. No query, no scoring.
  - Execute: runs the live query against inventory. Results are not
    persisted unless the user acts on them.
- mqi_qualified, mqi_rejection_reasons, mqi_qualified_at are POC artifacts
  and will be removed once the Phase 4 query-time filter is live.

---

## Deal Score Weights

Decision (2026-05-28): deal_score_weights is stored as a top-level scalar
column on filter_profiles and as a top-level field on FilterState, parallel
to rehab_cost_per_sqft and other engine configuration columns. It is NOT
embedded inside filter_criteria.filters.

Rationale: deal_score_weights governs pipeline behaviour (scoring), not
property selection (filtering). The filter_criteria JSONB blob is the
vocabulary for WHERE clause construction only. Engine configuration columns
are scalar columns on the ORM model for the same reason rehab_cost_per_sqft
is a scalar — they are first-class operational parameters, not filter
dimensions.

Default weights: arv_spread_score=0.50, signal_tier_score=0.25,
dom_score=0.15, absentee_score=0.10. Sum to 1.00. Lead with financial
outcome, treat seller motivation as secondary. dom_score intentionally
small — most inventory has no listing_event and the weight self-adjusts
to zero for unlisted properties via the total_weight normalization in
_compute_deal_score().

Existing profiles with empty deal_score_weights dict ({}) will fall back
to these defaults silently on first hydration via profileToFilterState().
No migration required.

---

## Search Architecture

- Current state: Option C hybrid (item 104). Lightweight scoring fetch
  (5 columns) for all filtered rows. Full ORM hydration scoped to page
  slice only (25 rows). Both search routes unified through _execute_search.
- All filtered rows loaded into Python for scoring and sorting before
  pagination is applied. max_results cap is a known limitation — users
  with broad filters receive a silently truncated result set.
- Target state: Option A — full SQL ORDER BY / LIMIT / OFFSET, migrating
  to keyset/cursor pagination at scale. Prerequisite: deal scoring engine 
  scoring dimensions must be expressible as SQL expressions. Current Python-side 
  scoring uses parcel_sale_history join logic that is not yet directly 
  expressible in SQL — this is the blocking constraint for Option A, not item 19.
- The ORDER BY county_fips, parcel_id tiebreaker (item 102) must be
  preserved through any search architecture migration — it is the
  foundation for keyset pagination.
- 65 remaining counties are staged. Python-side sort-then-slice will
  become untenable at multi-million row scale. Option A migration is
  a pre-statewide-launch requirement, not optional polish.

---

## Workflow Status Transition Map

Valid workflow_status values on listing_events:
  NEW | REVIEWED | APPROVE_SEND | SENT | RESPONDED | REJECTED | CLOSED

Enforced server-side in routes/listings.py PATCH status endpoint.
No transition outside this map is permitted — returns 422.
CLOSED is terminal. A new scrape event for the same parcel produces
a new listing_events row.

| From         | Permitted transitions                 |
|--------------|---------------------------------------|
| NEW          | REVIEWED, REJECTED                    |
| REVIEWED     | APPROVE_SEND, REJECTED                |
| APPROVE_SEND | SENT, REVIEWED                        |
| SENT         | RESPONDED, CLOSED, REJECTED           |
| RESPONDED    | CLOSED, REVIEWED                      |
| REJECTED     | REVIEWED, CLOSED                      |
| CLOSED       | (terminal — no transitions permitted) |

---

## Auth Model

- JWT HS256 via PyJWT. sub = users.id as string. email included as display
  hint only — never used for identity lookup.
- Token payload: sub, email, type="access", iat, exp.
- Password hashing: bcrypt direct. passlib dropped — incompatible with
  bcrypt 4.0+.
- get_current_user: decodes JWT, extracts user id, loads User from DB,
  raises 401 on failure or inactive user.
- require_county_access: superuser bypass, otherwise checks
  user_county_access for (user_id, county_fips) row, raises 403 on denial.
- Auth routes: POST /auth/token, GET /auth/me only.
  Registration, password reset, user management deferred to Phase 4.

---

## require_county_access — Dependency Pattern

The explicit await call pattern is replaced by the county_access() factory
function. Enforcement is declarative and impossible to omit — removing
Depends(county_access()) also removes the path parameter.

  Standard pattern — always use Depends, never call directly:

    @router.get("/{county_fips}/properties")
    async def list_properties(
        county_fips: str = Depends(county_access()),
        db: AsyncSession = Depends(get_db),
    ) -> ...:
        ...

- county_access() binds to path param named 'county_fips' by default.
- county_access("fips") if the path param has a different name.
- current_user is available inside the factory but NOT injected into the
  route. Routes that need the user object declare it separately:
  current_user: User = Depends(get_current_user)
- Superusers bypass user_county_access check entirely.
- Every county-scoped route must declare
  county_fips: str = Depends(county_access()).
  Non-county routes are exempt.

---

## Settings Import Convention

All files under real_invest_fl/ import settings as:
    from config.settings import settings
NOT as:
    from real_invest_fl.config.settings import settings

---

## Outreach Schema (v0.17)

### outreach_log lifecycle
- generate_outreach writes a DRAFT row and returns it.
- send_outreach accepts outreach_log_id, sends via SendGrid, updates
  sent_at and status = SENT. On failure: status = FAILED, send_error
  populated.
- Draft and sent state live on the same row. sent_at NULL means unsent.
- status domain: DRAFT | SENT | FAILED (CHECK constraint live).
- outreach_log.status is independent of listing_events.workflow_status.

### Re-generate blocking
- generate_outreach checks for an existing listing_scores row for
  (listing_event_id, filter_profile_id) before writing.
- If one exists, route returns a warning payload instead of a new draft.
- User must explicitly pass force=true to proceed.
- On force=true: new outreach_log draft row created. Existing
  listing_scores row is NOT overwritten — uq_ls_event_profile enforces
  this.

### Snapshot pattern
- recipient fields, calendar_link, skip_trace_result, and template_type
  are all snapshotted at generate time. The audit record is self-contained.
- calendar_link snapshotted from users.calendar_link. If the user changes
  their link after drafting, the draft retains the original.

### Cascade rules
- user_id: CASCADE. listing_event_id: CASCADE. filter_profile_id: SET NULL.
  template_id: RESTRICT. listing_score_id: SET NULL.

### outreach_templates
- Mirrors filter_profiles system/user pattern.
- county_fips nullable: NULL = global template.
- template_type: EMAIL | LETTER (CHECK constraint live).
- subject_template nullable — EMAIL only.

### skip_trace_cache
- One cached result per (county_fips, parcel_id) — uq_stc_county_parcel.
- TTL controlled by settings.SKIP_TRACE_CACHE_TTL_DAYS.
- Live BatchData API integration deferred (item 44). Route returns 501
  when BATCHDATA_API_KEY not configured.

### Email send path
- Provider: SendGrid Python SDK.
- CAN-SPAM compliance: every outgoing EMAIL must include
  settings.BUSINESS_ADDRESS as footer. Not optional.

### LETTER output path
- No server-side PDF. React react-to-print + window.print().
- FastAPI renders Jinja2 LETTER body and returns rendered string.
  React mounts hidden print-targeted component, calls window.print().

### users.calendar_link
- VARCHAR(1000) nullable. Any booking service supported.
- Snapshotted to outreach_log.calendar_link at generate time.
- UI must warn at generate time if current_user.calendar_link is NULL
  and the selected template is the system EMAIL template.

### Superuser scope on list_outreach
- Superusers see only their own outreach_log rows.
- Superuser privilege is county access bypass, not data omniscience.

---

## Dashboard Metrics Model

The dashboard is a user-activity view. It never surfaces raw inventory
counts or listing_events rows. Signals have no meaning outside a search
execution context and do not appear on the dashboard.

### What GET /dashboard returns
- Profile activity list: user_profile_prefs rows joined to filter_profiles
  for the current user, ordered by is_favorite DESC,
  last_searched_at DESC NULLS LAST, run_count DESC. Each entry carries
  profile_id, profile_name, county_fips, is_system, is_favorite,
  last_searched_at, last_result_count, run_count.
- Outreach pipeline status: drafts_pending (status = DRAFT),
  sent_this_week (sent_at >= now() - 7 days), responses_received
  (workflow_status = RESPONDED on linked listing_events, last 30 days).

### What GET /dashboard never returns
- Total property counts of any kind.
- Per-county raw inventory counts.
- listing_events rows.
- Any data shaped or filtered by a filter profile.

### Rationale
The dashboard represents what the user has done and what is ready to act
on. This mirrors the ChartMill screener pattern: the dashboard shows your
saved screens and their last output, not the size of the market.

---

## Map Interaction Model — ResultsPage (2026-05-23)

Three interaction paths exist in ResultsPage and are intentionally kept
distinct.

- Table row click: opens the property detail drawer only. Does not
  move the map camera. Does not open a popup.
- Map marker click: recenters the map via easeTo, opens the popup,
  highlights the corresponding table row, and scrolls it into view.
- "See on map" (drawer): closes the drawer, recenters the map via
  easeTo, and opens the popup. The drawer does not remain open because
  mobile viewports cannot display both simultaneously.

Map camera control is encapsulated in centerMapOnResult using
mapRef.current?.easeTo({ center: [longitude, latitude], zoom: 14,
duration: 800 }). MapRef is imported from react-map-gl/maplibre.
flyTo was considered but easeTo was used by the implementing agent.

The onLocate prop on PropertyDrawer is typed (() => void) | null
rather than optional to force explicit passing at every call site. When
selectedResult.latitude or selectedResult.longitude is null, null
is passed and the "See on map" button does not render.

The popup clears automatically when the page changes via a useEffect
on the page state variable. Only pageResults pins are rendered at any
time — never the full result set — to avoid DOM performance degradation
at scale.

PropertyDrawer useEffect includes a stale-async guard: an active
boolean is set to false on cleanup, preventing state updates from
in-flight fetches after unmount or selection change. detail and error
reset to null on every selection change.

---

## user_profile_prefs Table (v0.18)

Stores per-user, per-profile activity and bookmark state. One row per
(user_id, profile_id), created on first run or first favorite toggle.

- is_favorite: pure UI bookmark. No functional weight. Not used by
  the scheduler or any background process.
- Run tracking is user-scoped regardless of whether the profile is system
  or user-owned. Two users running the same system profile produce two
  separate rows.
- Aggregate only — no run log. last_searched_at, last_result_count, and
  run_count are sufficient for dashboard ordering.
- Cascade rules: user deleted → row deleted. Profile deleted → row deleted.

### Write pattern
GET /properties upserts after every successful result fetch:
increment run_count, set last_searched_at = now(),
set last_result_count = len(results).

PATCH /profiles/{profile_id}/favorite toggles is_favorite.
Creates the row if it does not exist (run_count = 0,
last_searched_at = NULL). No request body. Returns { "is_favorite": bool }.

Full schema in context/schema.md.
