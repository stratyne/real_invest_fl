# Project Penstock — context/arv.md
# Paste this alongside AGENTS.md when working on ARV calculation,
# deal scoring, or the comp engine.
# Last updated: 2026-05-26

## Status

PENDING — arv_calculator.py requires refactor before use (item 17).
Do not run current arv_calculator.py — mqi_qualified drift present.

## Key Files

real_invest_fl/ingest/
  arv_calculator.py     -- PENDING REFACTOR — do not use current version

## Data Sources (verified 2026-05-26)

### parcel_sale_history
- Santa Rosa: growing — ~56,858 parcels enriched as of 2026-05-26, run active
- Escambia: restarted 2026-05-26 after column mapping fix (item 101).
  ~3,060 parcels enriched. Previous corrupted rows deleted — all current rows are clean.
- Date range: varies by county, full historical ownership chain per parcel
- All records have sale_price > 0
- Populated from CAMA scrape — grows as CAMA runs continue
- **This is the primary comp source for the ARV engine.**

### NAL embedded sale fields (properties table)
- sale_prc1, sale_yr1, sale_mo1, qual_cd1 — most recent qualifying sale
- sale_prc2, sale_yr2, sale_mo2, qual_cd2 — second most recent
- NAL is an annual snapshot — carries only two most recent sales per parcel
- **Last-resort fallback only.** Used when parcel_sale_history has no
  qualifying records for a subject parcel's neighborhood. Never used
  for comp selection when parcel_sale_history data is available.
- Do not conflate NAL qual codes with parcel_sale_history qualification
  fields — they are entirely independent systems. See section below.

## Two Independent Qualification Systems

parcel_sale_history and the NAL embedded sale fields use entirely different
qualification schemes. They must never be conflated or cross-applied.
The qual_cd1/qual_cd2 fields on properties have no meaning in the context
of parcel_sale_history rows. The instrument_type/qualification_code fields
on parcel_sale_history have no relationship to Florida DOR qual codes.

### System 1 — parcel_sale_history qualification fields
Applied when parcel_sale_history is the comp source (primary path).
PA-level fields scraped directly from county parcelcard sites.

Three distinct columns — do not conflate:

- instrument_type VARCHAR(10): deed instrument type.
  Values: WD (Warranty Deed), QD (Quit Claim Deed), CT (Court/Certificate),
  SW (Sheriff's Warrant), TD (Tax Deed), PR (Personal Representative),
  PB (Probate), LD (Lady Bird Deed), DD (Dissolution Deed),
  FJ (Final Judgment), and others.
  Not all counties surface this field — NULL where unavailable.

- qualification_code VARCHAR(5): PA-level arms-length qualification flag.
  Confirmed values: Q = Qualified (arms-length), U = Unqualified,
  V = Vacant land.
  C = observed in Santa Rosa data — meaning UNCONFIRMED as of 2026-05-26.
  Treat 'C' as non-qualified until verified. Verification method: pull
  10-20 Santa Rosa parcelcard pages for parcels where qualification_code = 'C'
  and confirm the PA's stated meaning. This is a required step before the
  ARV engine assigns any meaning to 'C' other than non-qualified.

- sale_type VARCHAR(5): improved/vacant classification at time of sale.
  Values: I = Improved, V = Vacant.
  Santa Rosa only — Escambia does not surface this field.

Arms-length filter for comp selection (primary pool):
  instrument_type = 'WD' AND qualification_code = 'Q' AND sale_price >= 10000

Wider comp pool (use when primary pool yields fewer than min_comp_sales_for_arv):
  instrument_type = 'WD' AND qualification_code IN ('Q', 'U') AND sale_price >= 10000

The $10,000 minimum excludes nominal consideration deeds — 555 WD sales
between $1-$499 confirmed in Escambia data as non-arms-length transfers.

County logic is identical. Do not apply county-specific branching in the
ARV engine — fix the data, not the query.

### System 2 — NAL embedded qualification codes (properties.qual_cd1 / qual_cd2)
Applied only when falling back to NAL embedded sale fields (last-resort path).
Never used for comp selection from parcel_sale_history.
Florida DOR numeric qualification codes.

| qual_cd | Description                        | ARV Use                              |
|---------|------------------------------------|--------------------------------------|
| 01      | Qualified arm's-length sale        | PRIMARY — last-resort fallback pool  |
| 02      | Qualified, multiple parcels        | Usable with caution                  |
| 03      | Qualified, foreclosure             | Distressed comp signal               |
| 11      | Disqualified — corrective deed     | EXCLUDE                              |
| 12      | Disqualified — related parties     | EXCLUDE                              |
| 14      | Disqualified — transfer            | EXCLUDE                              |
| 30      | Disqualified — non-arm's length    | EXCLUDE                              |
| 37      | Disqualified — REO/bank owned      | EXCLUDE from ARV; distressed signal  |
| 05      | Disqualified — financial           | EXCLUDE                              |
| All others | Various disqualified           | EXCLUDE                              |

Santa Rosa verified qual_cd distribution (dor_uc='001', 2024-2025):
- '01': 4,884 records, avg $380,977 — primary fallback pool
- '02': 1,493 records, avg $509,433
- '11': 1,860 records — excluded
- '14': 1,428 records — excluded
- All others: smaller counts, excluded per table above

## ARV Comp Engine Design

### Primary Path — parcel_sale_history

- Source: parcel_sale_history joined to properties on
  (county_fips, parcel_id) for subject parcel geometry and attributes
- Qualification filter: instrument_type = 'WD' AND qualification_code = 'Q'
  AND sale_price >= 10000 (primary pool).
  Widen to qualification_code IN ('Q', 'U') when primary pool yields
  fewer than min_comp_sales_for_arv qualifying comps.
- Proximity filter: comp_radius_miles from filter_profile, applied via
  PostGIS ST_DWithin against properties.geom. Requires GIST index on geom.
  Comp parcels joined to properties to retrieve geometry for spatial filter.
- Year built filter:
  ABS(comp.eff_yr_blt - subject.eff_yr_blt) <= comp_year_built_tolerance
  from filter_profile
- Use code filter: comp parcel dor_uc must match subject parcel dor_uc
- Minimum comps: min_comp_sales_for_arv from filter_profile
- Calculation: median(sale_price / tot_lvg_area) of qualifying comps
  multiplied by subject parcel tot_lvg_area
- arv_source: 'COMP'

### Fallback Path — NAL embedded fields

Used only when parcel_sale_history yields zero qualifying comp candidates
within the search radius for the subject parcel. Not a substitute for
a thin parcel_sale_history — if the history table has records but they
fail the arms-length filter, the fallback does NOT trigger. The fallback
triggers only on zero candidates after all filters are applied.

- Source: properties.sale_prc1, sal_yr1, qual_cd1 (and _2 variants)
  for properties within comp_radius_miles of subject parcel
- Qualification filter: qual_cd1 = '01' (primary). qual_cd1 = '02'
  usable with caution. All other codes excluded.
- Minimum price filter: sale_prc1 >= 10000
- Calculation: median(sale_prc1 / tot_lvg_area) of qualifying neighbors
  multiplied by subject parcel tot_lvg_area
- arv_source: 'JV_FALLBACK'
- Note: if NAL fallback also yields zero qualifying comps, arv_estimate
  is set to properties.jv and arv_source is 'JV_FALLBACK'. jv is the
  floor — never NULL-out arv_estimate.

### arv_source Values

| Value        | Meaning                                                    |
|--------------|------------------------------------------------------------|
| COMP         | Calculated from parcel_sale_history qualifying comps       |
| JV_FALLBACK  | Insufficient comps — jv used as proxy, or NAL fallback     |
| ZESTIMATE    | Zestimate used (future — item 21)                          |
| MANUAL       | Manually set                                               |

COMP and JV_FALLBACK are not equivalent. Surface arv_source in all
result views — do not display them with equal visual weight.

### arv_spread Calculation

arv_spread = arv_estimate - list_price - rehab_cost_estimate
rehab_cost_estimate = tot_lvg_area x (properties.estimated_rehab_per_sqft
                      OR filter_profile.rehab_cost_per_sqft)

list_price is NULL for off-market properties. arv_spread is NULL when
list_price is NULL. Do not substitute 0 for NULL list_price.

## filter_profile Parameters Relevant to ARV

rehab_cost_per_sqft         FLOAT    -- fallback when properties.estimated_rehab_per_sqft is NULL
min_comp_sales_for_arv      INTEGER  -- minimum qualifying comps before COMP arv_source is used
comp_radius_miles           FLOAT    -- proximity radius for comp selection
comp_year_built_tolerance   INTEGER  -- +/- years built tolerance for comp selection

## Escambia Data State (as of 2026-05-26)

Escambia CAMA scraper column mapping bug was confirmed and fixed (item 101).
All previously scraped Escambia parcel_sale_history rows were deleted.
Run restarted 2026-05-26 — all current Escambia rows are clean.
~3,060 parcels enriched as of restart. qualification_code is populated
correctly on all new rows. instrument_type is NULL for Escambia —
parcelcard does not surface this field.

IMPORTANT: With instrument_type = NULL for all Escambia rows, the primary
arms-length filter (instrument_type = 'WD' AND qualification_code = 'Q')
will return zero Escambia comp candidates. The ARV engine will fall back
to the NAL path or jv for all Escambia parcels until the parcelcard
begins surfacing instrument_type, or a county-specific qualification
strategy is confirmed. This is a known data limitation, not an engine bug.
Do not add county-specific branching to work around it — document it here
and revisit when Escambia comp pool is verified post-full-run.

## Santa Rosa Data State (as of 2026-05-26)

~56,858 parcels enriched, run active. qualification_code populated (Q/U/C/V).
instrument_type is NULL — parcelcard does not surface this field.

Same implication as Escambia: instrument_type = NULL means the primary
arms-length filter yields zero candidates for Santa Rosa as well.

REVISED ARMS-LENGTH FILTER FOR CURRENT DATA:
Since neither county surfaces instrument_type on their parcelcard,
the practical primary filter for both counties is:
  qualification_code = 'Q' AND sale_price >= 10000

And the wider pool is:
  qualification_code IN ('Q', 'U') AND sale_price >= 10000

The instrument_type = 'WD' condition should be applied only when
instrument_type IS NOT NULL, to avoid silently eliminating the entire
comp pool. Implement as:
  (instrument_type = 'WD' OR instrument_type IS NULL)
  AND qualification_code = 'Q'
  AND sale_price >= 10000

This is the correct filter given current data. Revisit if/when a county
parcelcard begins surfacing instrument_type.

## qualification_code = 'C' — Resolved (Santa Rosa)

'C' is a Santa Rosa PA-local qualification value meaning "Qualified and
Confirmed." Confirmed directly with Richard Brosnaham, Administrative
Coordinator, Santa Rosa County Property Appraiser's Office, 2026-05-26.
Contact: 850.983.1880.

'C' represents an arms-length qualified sale where the PA has taken an
additional confirmation step beyond standard 'Q' qualification. It is
not a Florida DOR transfer code — it is Santa Rosa's internal value in
the parcelcard Q/U column.

Data profile (verified 2026-05-26, sale_price >= 10000):
- 6,941 records (6,510 improved, 417 vacant)
- Improved avg: $408,045
- Vacant avg: $96,040
- Instrument type: WD throughout sampled records
- Active through 2026

ARV engine treatment: 'C' is at least equal confidence to 'Q' and may
be treated as higher confidence given the additional confirmation step.
Primary comp pool: qualification_code IN ('Q', 'C') AND sale_price >= 10000
Wider pool: qualification_code IN ('Q', 'C', 'U') AND sale_price >= 10000

## bed_bath_source Confidence Hierarchy

Never overwrite an existing beds/baths value with a lower-confidence source.
Confidence order (highest to lowest):

1. cama          — PA parcelcard, most authoritative
2. county_clerk  — direct county government source. Current clerk sources
                   (lis pendens, foreclosure, tax deed) are legal event records
                   and do NOT carry beds/baths. Reserved for future county
                   sources that surface building characteristics.
3. zillow_staging / auction_com — equal confidence, third-party sourced
4. manual        — lowest, human-entered, no current write workflow

auction_com sentinel rule: total_bedrooms=0 and total_bathrooms=0 are
missing-data sentinels — treat as None, never write to DB.

Phase 3 sources (Landvoice, REDX, PropStream): slot at zillow_staging /
auction_com level until data quality is evaluated.

If incoming source confidence equals existing, overwrite (fresher data
from same source is acceptable). If lower, skip entirely.
Logic lives in the parser layer. Not yet implemented — implementation
is part of item 17 scope.

## Multi-year SDF (Florida DOR Sales Data File)

DEFERRED — not a dependency. parcel_sale_history + NAL qual codes provide
sufficient comp pool for the ARV engine. SDF improves comp pool depth and
geographic coverage when it arrives. Contact: PTOTechnology@floridarevenue.com
Do not raise SDF as a blocker — this decision is locked (2026-05-04).

## New County Checklist Addition

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

And qualification code distribution:

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

And parcel_sale_history qualification distribution:

  SELECT
      instrument_type,
      qualification_code,
      COUNT(*)              AS count,
      ROUND(AVG(sale_price)) AS avg_price
  FROM parcel_sale_history
  WHERE county_fips = '{fips}'
  AND sale_price >= 10000
  GROUP BY instrument_type, qualification_code
  ORDER BY count DESC;

Minimum viable comp pool: 1,000+ qualification_code = 'Q' records
for the county before COMP arv_source is considered reliable.
