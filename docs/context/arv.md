# Project Penstock — context/arv.md
# Paste this alongside AGENTS.md when working on ARV calculation,
# deal scoring, or the comp engine.
# Last updated: 2026-05-28

## Status

ACTIVE — arv_calculator.py refactor complete (item 17).
Santa Rosa first pass complete. --force re-run pending second CAMA pass
completion (2,265 retry parcels). Escambia pending sufficient CAMA
enrichment before first run.

## Key Files

real_invest_fl/ingest/
  arv_calculator.py     -- ACTIVE — three-pass comp engine, item 17 complete

## Data Sources (verified 2026-05-28)

### parcel_sale_history
- Santa Rosa: 66,047 parcels enriched (dor_uc '001' only).
  Second pass active — 2,265 retry parcels. Completion imminent.
  54,453 unenriched parcels have dor_uc outside scraper target list —
  they are not SFR and will not be scraped by santa_rosa.py.
- Escambia: ~18,448 parcels enriched as of 2026-05-28, run active.
  All current rows are clean (column mapping fix applied item 101).
  instrument_type is NULL for all Escambia rows — parcelcard does not
  surface this field.
- Date range: varies by county, full historical ownership chain per parcel
- All records have sale_price > 0
- Populated from CAMA scrape — grows as CAMA runs continue
- **This is the primary comp source for the ARV engine.**

### NAL embedded sale fields (properties table)
- sale_prc1, sale_yr1, sale_mo1, qual_cd1 — most recent qualifying sale
- sale_prc2, sale_yr2, sale_mo2, qual_cd2 — second most recent
- NAL is an annual snapshot — carries only two most recent sales per parcel
- **Pass 3 fallback only.** Used when parcel_sale_history Passes 1 and 2
  yield fewer than min_comp_sales_for_arv qualifying comps.
- qual_cd2 is not used in Pass 3 — two-field NAL history is too thin
  to reliably widen; jv floor is preferable to noisy qual_cd2 comps.
- Do not conflate NAL qual codes with parcel_sale_history qualification
  fields — they are entirely independent systems. See section below.

## Two Independent Qualification Systems

parcel_sale_history and the NAL embedded sale fields use entirely different
qualification schemes. They must never be conflated or cross-applied.
The qual_cd1/qual_cd2 fields on properties have no meaning in the context
of parcel_sale_history rows. The instrument_type/qualification_code fields
on parcel_sale_history have no relationship to Florida DOR qual codes.

### System 1 — parcel_sale_history qualification fields
Applied in Pass 1 and Pass 2 of the comp engine.
PA-level fields scraped directly from county parcelcard sites.

Three distinct columns — do not conflate:

- instrument_type VARCHAR(10): deed instrument type.
  Values: WD (Warranty Deed), QD (Quit Claim Deed), CT (Court/Certificate),
  SW (Sheriff's Warrant), TD (Tax Deed), PR (Personal Representative),
  PB (Probate), LD (Lady Bird Deed), DD (Dissolution Deed),
  FJ (Final Judgment), and others.
  Not all counties surface this field — NULL where unavailable.
  Neither Santa Rosa nor Escambia currently surfaces instrument_type.

- qualification_code VARCHAR(5): PA-level arms-length qualification flag.
  Confirmed values:
    Q = Qualified (arms-length)
    U = Unqualified
    V = Vacant land
    C = Qualified and Confirmed (Santa Rosa PA-local value — confirmed
        2026-05-26 by Richard Brosnaham, Administrative Coordinator,
        Santa Rosa County PA. Contact: 850.983.1880.)
  'C' is arms-length qualified with additional PA confirmation step.
  Treat as equal or higher confidence than 'Q' for comp selection.

- sale_type VARCHAR(5): improved/vacant classification at time of sale.
  Values: I = Improved, V = Vacant.
  Santa Rosa only — Escambia does not surface this field.

Arms-length filter (primary pool — Pass 1):
  (
      qualification_code IN ('Q', 'C')
      OR (qualification_code IS NULL AND instrument_type = 'WD')
  )
  AND sale_price >= 10000

The OR branch fires for counties where qualification_code is NULL
across all rows but instrument_type is populated (currently Escambia).
For Santa Rosa, qualification_code is always populated so the first
branch fires. For Escambia, qualification_code is always NULL so the
WD branch fires. No county-specific branching in code — the filter is
self-selecting by county data shape.

Arms-length filter (wider pool — Pass 2):
  (
      qualification_code IN ('Q', 'C', 'U')
      OR (qualification_code IS NULL AND instrument_type = 'WD')
  )
  AND sale_price >= 10000

County viability pre-flight uses the same filter as Pass 1 to correctly
assess counties without qualification_code as viable when WD records exist.

Arms-length filter (wider pool — Pass 2):
  (instrument_type = 'WD' OR instrument_type IS NULL)
  AND qualification_code IN ('Q', 'C', 'U')
  AND sale_price >= 10000

The instrument_type IS NULL condition is required — neither current county
surfaces instrument_type on their parcelcard. Applying instrument_type = 'WD'
alone would silently eliminate the entire comp pool. Revisit if/when a
county parcelcard begins surfacing instrument_type.

The $10,000 minimum excludes nominal consideration deeds — 555 WD sales
between $1-$499 confirmed in Escambia data as non-arms-length transfers.

County logic is identical. Do not apply county-specific branching in the
ARV engine — fix the data, not the query.

### System 2 — NAL embedded qualification codes (properties.qual_cd1)
Applied in Pass 3 (NAL spatial fallback) only.
Never used for comp selection from parcel_sale_history.
Florida DOR numeric qualification codes.

| qual_cd | Description                        | ARV Use                         |
|---------|------------------------------------|---------------------------------|
| 01      | Qualified arm's-length sale        | PRIMARY — Pass 3 comp pool      |
| 02      | Qualified, multiple parcels        | NOT used — see note below       |
| 03      | Qualified, foreclosure             | Distressed comp signal          |
| 11      | Disqualified — corrective deed     | EXCLUDE                         |
| 12      | Disqualified — related parties     | EXCLUDE                         |
| 14      | Disqualified — transfer            | EXCLUDE                         |
| 30      | Disqualified — non-arm's length    | EXCLUDE                         |
| 37      | Disqualified — REO/bank owned      | EXCLUDE from ARV                |
| 05      | Disqualified — financial           | EXCLUDE                         |
| All others | Various disqualified           | EXCLUDE                         |

Note on qual_cd '02': arv.md previously listed '02' as usable with caution.
Pass 3 uses qual_cd1 = '01' only. qual_cd2 is not used at all — two-field
NAL history is too thin to reliably widen the pool; jv floor is preferable
to noisy qual_cd2 comps. This is a deliberate scope constraint, not an
oversight.

Santa Rosa verified qual_cd distribution (dor_uc='001', 2024-2025):
- '01': 4,884 records, avg $380,977 — Pass 3 pool
- '02': 1,493 records, avg $509,433 — excluded
- '11': 1,860 records — excluded
- '14': 1,428 records — excluded
- All others: smaller counts, excluded per table above

## ARV Comp Engine Design

### Three-Pass Strategy

Pass 1, Pass 2, and Pass 3 are attempted in sequence for all Tier 1
parcels (jv IS NOT NULL AND geom IS NOT NULL). Each pass is only
attempted if the previous pass yielded fewer than min_comp_sales_for_arv
qualifying comps. Non-viable counties (below MIN_VIABLE_COMP_POOL
threshold) skip Passes 1 and 2 and go directly to Pass 3.

### Pass 1 — parcel_sale_history primary pool

- Source: parcel_sale_history joined to properties on
  (county_fips, parcel_id) for comp geometry and attributes
- Qualification filter:
  (instrument_type = 'WD' OR instrument_type IS NULL)
  AND qualification_code IN ('Q', 'C')
  AND sale_price >= 10000
- Proximity filter: ST_DWithin against comp properties.geom using
  radius_meters derived from --radius CLI flag
- Year built filter:
  ABS(comp.eff_yr_blt - subject.eff_yr_blt) <= year_tolerance
- Use code filter: comp parcel dor_uc must match subject parcel dor_uc
- Minimum comps: min_comp_sales_for_arv
- Calculation: median(sale_price / comp.tot_lvg_area) * subject.tot_lvg_area
- arv_source: 'COMP'

### Pass 2 — parcel_sale_history wider pool

- Triggered when Pass 1 yields fewer than min_comp_sales_for_arv comps
- Identical to Pass 1 except:
  qualification_code IN ('Q', 'C', 'U')
- arv_source: 'COMP'

### Pass 3 — NAL spatial fallback

- Triggered when Pass 2 also yields fewer than min_comp_sales_for_arv comps
- Source: properties.sale_prc1, qual_cd1 for neighboring parcels
- Qualification filter: qual_cd1 = '01' AND sale_prc1 >= 10000
- Proximity filter: ST_DWithin — same radius as Passes 1 and 2
- Year built filter: same tolerance as Passes 1 and 2
- Use code filter: neighboring parcel dor_uc must match subject dor_uc
- Minimum comps: min_comp_sales_for_arv
- Calculation: median(sale_prc1 / neighbor.tot_lvg_area) * subject.tot_lvg_area
- arv_source: 'NAL_COMP'
  (NAL spatial fallback comp calculation — lower confidence than
  parcel_sale_history COMP but a real comp calculation, not a raw jv
  substitution. Do not display with equal visual weight to COMP or
  equal visual weight to JV_FALLBACK floor.)
- qual_cd2 is not used — see System 2 note above

### Floor — raw jv

- Triggered when Pass 3 also yields fewer than min_comp_sales_for_arv comps
- arv_estimate = jv
- arv_source = 'JV_FALLBACK'
- jv is the floor — never NULL-out arv_estimate

### Two-Tier Eligibility Gate

Tier 1 — jv IS NOT NULL AND geom IS NOT NULL
  Full three-pass strategy attempted.

Tier 2 — jv IS NOT NULL AND geom IS NULL
  No spatial query possible. arv_estimate = jv, arv_source = JV_FALLBACK
  written directly. No passes attempted.

Excluded — jv IS NULL
  Skipped entirely. Count logged. No write.

dor_uc is not part of the gate. ARV is computed for all property classes.
dor_uc is used as a like-for-like filter within comp selection only.

### arv_source Values

| Value        | Meaning                                                              |
|--------------|----------------------------------------------------------------------|
| COMP         | Calculated from parcel_sale_history qualifying comps (Pass 1/2)      |
| NAL_COMP     | Calculated from NAL embedded sale_prc1 on neighboring parcels (Pass 3)|
| JV_FALLBACK  | Raw jv used — no geom, or all passes yielded insufficient comps      |
| ZESTIMATE    | Zestimate used (future — item 21)                                    |
| MANUAL       | Manually set                                                         |

COMP and JV_FALLBACK are not equivalent. Surface arv_source in all
result views — do not display them with equal visual weight.

### arv_spread Calculation

Batch script:
  arv_spread = arv_estimate - list_price - (tot_lvg_area * rehab_cost)
  rehab_cost = --rehab-cost CLI flag (default $35.00)
  NULL when list_price is NULL. NULL when tot_lvg_area is NULL or zero.
  Never substitute 0 for NULL list_price.

Search route (query-time recomputation):
  arv_spread = arv_estimate - list_price -
               (tot_lvg_area * profile.rehab_cost_per_sqft)
  The stored properties.arv_spread uses batch default rehab cost.
  Search routes always recompute using active profile's value.
  Export pipelines (items 20, 22) must also recompute — never read
  stored arv_spread directly.
  Cleanup migration (drop column, pure query-time everywhere) deferred
  until items 20 and 22 are in scope simultaneously.

## CLI Defaults and filter_profile Parameters

### Batch script CLI defaults
  --radius          1.5 miles
  --min-comps       3
  --year-tolerance  10
  --rehab-cost      $35.00

### filter_profile columns relevant to ARV (query-time)
  rehab_cost_per_sqft         FLOAT    -- used for query-time arv_spread recompute
  min_comp_sales_for_arv      INTEGER  -- not used at batch time, query-time reference
  comp_radius_miles           FLOAT    -- not used at batch time, query-time reference
  comp_year_built_tolerance   INTEGER  -- not used at batch time, query-time reference

## County Viability Pre-flight

Threshold: 1,000+ records meeting the arms-length filter:
  (qualification_code IN ('Q', 'C')
   OR (qualification_code IS NULL AND instrument_type = 'WD'))
  AND sale_price >= 10000
Previously used qualification_code IN ('Q', 'C') only — this caused
Escambia (qualification_code NULL, instrument_type populated) to be
assessed as non-viable and skip Passes 1+2 entirely. Fixed 2026-05-29.
Counties below threshold skip Passes 1 and 2 entirely.
Pass 3 (NAL spatial fallback) is always attempted for all Tier 1 parcels
regardless of county viability.
Purpose of pre-flight: log clarity, not performance.

## Re-run Triggers

Run arv_calculator.py after:
  - CAMA scrape completion for a county (new parcel_sale_history data)
  - Annual NAL refresh (updated jv, tot_lvg_area, sale fields)

Always use --force when re-running after data changes — the resume
filter (arv_estimate IS NULL) will skip all previously calculated parcels.
Always scope to --county when practical to avoid unnecessary re-computation
of already-current counties.

## Santa Rosa Data State (as of 2026-05-29)

CAMA complete: 68,303 / 68,312 enriched.
ARV re-run pending (item 125).
tot_lvg_area corrected: 67,543 rows restored from raw_cama_json —
NAL re-ingest had overwritten CAMA heated area (2,439 sqft) with NAL
effective area (2,803 sqft). CAMA wins for tot_lvg_area going forward
(_NAL_UPSERT_NEVER_OVERWRITE).
instrument_type: NULL for all parcelcard-sourced rows. Will be
backfilled by santa_rosa_sales.py (item 124) from srcpa.gov/parcel.
qualification_code populated: Q / U / C / V.
parcel_sale_history: 152,909 records, source srcpa_parcelcard.
57,987 parcels truncated at 2 sales — full history pending item 124.

## Escambia Data State (as of 2026-05-29)

~27,284 / 106,372 SFR parcels enriched, CAMA run active.
beds/baths/cama_quality_code absent from Escambia parcelcard — NULL permanent.
instrument_type populated in parcel_sale_history: WD, QC, OT, CJ, CT, etc.
qualification_code: NULL for all Escambia parcel_sale_history rows —
parcelcard does not surface it. ARV engine uses WD fallback branch.
County viability pre-flight now correctly assesses Escambia as VIABLE
based on WD record count. Passes 1+2 will fire on ARV run.
ARV first run pending CAMA completion (item 125).
own_state_dom: NULL for 170,491 of 170,561 rows — Escambia PA does
not populate this NAL field. Out-of-state owner filter non-functional
for Escambia on this dimension.

## bed_bath_source Confidence Hierarchy

Never overwrite an existing beds/baths value with a lower-confidence source.
Confidence order (highest to lowest):

1. cama          — PA parcelcard, most authoritative
2. county_clerk  — direct county government source. Current clerk sources
                   (lis pendens, foreclosure, tax deed) are legal event
                   records and do NOT carry beds/baths. Reserved for future
                   county sources that surface building characteristics.
3. zillow_staging / auction_com — equal confidence, third-party sourced
4. manual        — lowest, human-entered, no current write workflow

auction_com sentinel rule: total_bedrooms=0 and total_bathrooms=0 are
missing-data sentinels — treat as None, never write to DB.

Phase 3 sources (Landvoice, REDX, PropStream): slot at zillow_staging /
auction_com level until data quality is evaluated.

If incoming source confidence equals existing, overwrite (fresher data
from same source is acceptable). If lower, skip entirely.
Logic lives in the parser layer. Not yet implemented — tracked as item 116.
scope completion for full bed_bath_source enforcement.

## Multi-year SDF (Florida DOR Sales Data File)

DEFERRED — not a dependency. parcel_sale_history + NAL qual codes provide
sufficient comp pool for the ARV engine. SDF improves comp pool depth and
geographic coverage when it arrives. Contact: PTOTechnology@floridarevenue.com
Do not raise SDF as a blocker — this decision is locked (2026-05-04).

## Phase 3 Scaling Limitation

Per-parcel spatial query at ~120ms/parcel is acceptable for current
2-county scope (~291K parcels, ~11 hour full run). At 67-county scale
(~8-10M parcels) this approach becomes untenable. Architecture options
at Phase 3: temp table pre-aggregation or partitioned bulk join.
County-wide bulk join was attempted and failed at Santa Rosa scale —
query did not complete after 4+ hours. Do not retry bulk join without
first resolving PostgreSQL work_mem and query planner configuration.
Documented in deferred item 115.

## New County Checklist

When a new county CAMA scrape completes, verify comp pool viability:

  SELECT
      COUNT(*)                    AS total_sales,
      COUNT(sale_price)           AS has_price,
      MIN(sale_date)              AS earliest_sale,
      MAX(sale_date)              AS latest_sale,
      COUNT(DISTINCT parcel_id)   AS distinct_parcels
  FROM parcel_sale_history
  WHERE county_fips = '{fips}'
  AND sale_price > 0;

Qualification code distribution:

  SELECT
      qual_cd1,
      COUNT(*)              AS count,
      ROUND(AVG(sale_prc1)) AS avg_price
  FROM properties
  WHERE county_fips = '{fips}'
  AND dor_uc = '001'
  AND sale_prc1 > 0
  AND qual_cd1 IS NOT NULL
  GROUP BY qual_cd1
  ORDER BY count DESC;

parcel_sale_history qualification distribution:

  SELECT
      instrument_type,
      qualification_code,
      COUNT(*)               AS count,
      ROUND(AVG(sale_price)) AS avg_price
  FROM parcel_sale_history
  WHERE county_fips = '{fips}'
  AND sale_price >= 10000
  GROUP BY instrument_type, qualification_code
  ORDER BY count DESC;

Minimum viable comp pool: 1,000+ qualification_code IN ('Q', 'C') records
for the county before COMP arv_source is considered reliable for Pass 1/2.
Pass 3 (NAL spatial fallback) is always available regardless of PSH pool size.
