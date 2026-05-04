# Project Penstock — context/arv.md
# Paste this alongside AGENTS.md when working on ARV calculation,
# deal scoring, or the comp engine.
# Last updated: 2026-05-04

## Status

PENDING — arv_calculator.py requires refactor before use (item 17).
Do not run current arv_calculator.py — mqi_qualified drift present.

## Key Files

real_invest_fl/ingest/
  arv_calculator.py     -- PENDING REFACTOR — do not use current version

## Data Sources (verified 2026-05-04)

### parcel_sale_history
- Santa Rosa: 35,340 sale records, 7,305 distinct parcels
- Date range: 1912-09-01 – 2026-04-17
- All records have sale_price > 0
- Populated from CAMA scrape (santa_rosa.py) — grows as CAMA run continues

### NAL embedded sale fields (properties table)
- sale_prc1, sale_yr1, sale_mo1, qual_cd1 — most recent qualifying sale
- sale_prc2, sale_yr2, sale_mo2, qual_cd2 — second most recent
- NAL is an annual snapshot — carries only two most recent sales per parcel
- Not a substitute for parcel_sale_history for comp purposes

## Florida DOR Qualification Codes

Used to filter arm's-length market transactions from non-market transfers.

| qual_cd | Description | ARV Use |
|---|---|---|
| 01 | Qualified arm's-length sale | PRIMARY comp pool |
| 02 | Qualified, multiple parcels | Usable with caution |
| 03 | Qualified, foreclosure | Distressed comp signal |
| 11 | Disqualified — corrective deed | EXCLUDE |
| 12 | Disqualified — related parties | EXCLUDE |
| 14 | Disqualified — transfer | EXCLUDE |
| 30 | Disqualified — non-arm's length | EXCLUDE |
| 37 | Disqualified — REO/bank owned | EXCLUDE from ARV; useful as distressed signal |
| 05 | Disqualified — financial | EXCLUDE |
| All others | Various disqualified | EXCLUDE |

Santa Rosa verified qual_cd distribution (dor_uc='001', 2024-2025):
- '01': 4,884 records, avg $380,977 — primary comp pool
- '02': 1,493 records, avg $509,433
- '11': 1,860 records — excluded
- '14': 1,428 records — excluded
- All others: smaller counts, excluded per table above

## ARV Comp Engine Design (locked)

- Primary source: parcel_sale_history joined to properties
- Qualification filter: qual_cd1 = '01' primary, '02' caution, '03' distressed
- Proximity filter: comp_radius_miles from filter_profile
- Year built filter: comp_year_built_tolerance from filter_profile
- Use code filter: dor_uc must match subject parcel
- Minimum comps: min_comp_sales_for_arv from filter_profile
- Calculation: median price per sqft of qualifying comps × subject tot_lvg_area
- Fallback: jv when comp count < min_comp_sales_for_arv
- arv_source values:
    'COMP'        — market comp calculation
    'JV_FALLBACK' — insufficient comps, jv used
    'ZESTIMATE'   — Zestimate used (future)
    'MANUAL'      — manually set

## filter_profile Parameters Relevant to ARV

rehab_cost_per_sqft         FLOAT    -- fallback when properties.estimated_rehab_per_sqft is NULL
min_comp_sales_for_arv      INTEGER  -- minimum qualifying comps required before COMP arv_source is used
comp_radius_miles           FLOAT    -- proximity radius for comp selection
comp_year_built_tolerance   INTEGER  -- +/- years built tolerance for comp selection

## arv_spread Calculation

arv_spread = arv_estimate - list_price - rehab_cost_estimate
rehab_cost_estimate = tot_lvg_area × (estimated_rehab_per_sqft OR filter_profile.rehab_cost_per_sqft)

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
    COUNT(*)            AS count,
    ROUND(AVG(sale_prc1)) AS avg_price
FROM properties
WHERE county_fips = '{fips}'
AND dor_uc = '001'
AND sale_prc1 > 0
AND qual_cd1 IS NOT NULL
GROUP BY qual_cd1
ORDER BY count DESC;

Minimum viable comp pool: 1,000+ qual_cd='01' records for the county.
