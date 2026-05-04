# Project Penstock — context/scrapers.md
# Paste this alongside AGENTS.md when working on scrapers, listing sources,
# address normalization, or parcel matching.
# Last updated: 2026-05-04

## Key Files

real_invest_fl/scrapers/
  __init__.py
  auction_com.py               -- COMPLETE
  base_scraper.py
  escambia_foreclosure.py      -- robots-blocked, retained for reference
  escambia_taxdeed_clerk.py    -- COMPLETE

real_invest_fl/ingest/
  listing_matcher.py           -- centralized parcel lookup
  run_auction_com.py           -- COMPLETE
  run_taxdeed.py               -- COMPLETE
  run_staging_import.py        -- routes to staging parsers
  source_status.py             -- data_source_status upsert helper

real_invest_fl/ingest/staging_parsers/
  __init__.py
  foreclosure_parser.py
  lis_pendens_parser.py
  tax_deed_parser.py
  zillow_parser.py             -- COMPLETE

real_invest_fl/utils/
  parcel_id.py                 -- normalize_parcel_id() — do NOT call in scrapers
  robots.py
  text.py                      -- normalize_street_address()
  
- Parser-layer bed/bath confidence hierarchy: deferred, not yet implemented.

## Scraper Source Tiers

| Tier | Sources | Approach | Status |
|---|---|---|---|
| 1 — Government direct | Escambia Clerk tax deed, lis pendens, foreclosures | Live scrape or file-drop | Tax deed complete; others file-drop |
| 2 — Public aggregators | Auction.com, HUD Home Store | Playwright + rate limiting | Auction.com COMPLETE |
| 3 — Free listing sources | Craigslist FSBO | requests + BS4 | DEFERRED indefinitely |
| 4 — Commercial platforms | Zillow, Redfin, Realtor.com | Paid API / vendor proxy | DEFERRED |

## Address Normalization

normalize_street_address() in real_invest_fl/utils/text.py
- Single shared normalizer for ALL scrapers and listing_matcher
- Transformations (in order):
  1. Upper-case
  2. Unit strip (runs BEFORE digit-letter injection)
  3. Digit-letter injection — regex: (\d)(?!(?:ST|ND|RD|TH)\b)([A-Z])
     Excludes ordinal suffixes: 74TH, 48TH pass through unchanged
  4. Suffix abbreviation
  5. Directional contraction
- strip_unit=False: preserves unit designators for Level 2 lookup
- strip_unit=True (default): strips units, used for dedup key
- `#` unit designator has no leading \b anchor — `#` is not a word char
- listing_matcher._normalize_address() delegates to normalize_street_address()

Address matching — three-level fallback in listing_matcher.py:
  Level 1: exact match
  Level 2: unit suffix normalization (#4A → 4A)
  Level 3: street prefix match with MULTI-UNIT review flag

Library: rapidfuzz v3.14.5

### Known Bug Fix (2026-05-01)
- Bug: digit-letter injection was incorrectly applied to the post-unit portion
  of the string when strip_unit=False.
- Fix: injection now confined to pre-unit portion only when strip_unit=False.
- Test coverage: 50 tests in address normalization suite + 2 additional tests
  in test_listing_matcher_lookup.py. All passing as of 2026-04-28.

## Parcel ID Rules in Scrapers

- Strip non-alphanumeric, uppercase, NO zero-padding
- Do NOT call normalize_parcel_id() — it zero-pads to 18 and will break the join
- Use raw strip+uppercase only

## Per-Scraper Notes

### auction_com.py
- _normalize_street() is intentionally minimal — digit-letter injection and
  upper/collapse only. Do not expand it.
- GraphQL API: POST https://graph.auction.com/graphql
- No auth required. x-cid header must be fresh UUID per request.
- Remove $hasAuthenticatedUser from operation signature AND variables.
- Returns 50-mile radius (~73 records).
  Filter: country_primary_subdivision=FL AND country_secondary_subdivision=ESCAMBIA
  (case-insensitive). 14-17 records survive.
- total_bedrooms=0 and total_bathrooms=0 are missing-data sentinels → None.
- Wired through listing_matcher.py lookup_parcel_by_address().
- NOT yet wired through BaseScraper discovery.
- Known unmatched: 2983 NORTH HIGHWAY 95 A → 2983 N HWY 95 A.
  Suspected NAL storage format mismatch, not a normalization defect.

### escambia_taxdeed_clerk.py
- Date list: https://public.escambiaclerk.com/taxsale/taxsaledates.asp
- Per-date: https://public.escambiaclerk.com/taxsale/taxsaleMobile.asp?saledate=M/D/YYYY
- saledate format: M/D/YYYY, no zero-padding, no percent-encoding.
  Build URL as string — NEVER use requests params dict for this.
- Table selector: soup.find("table", attrs={"bgcolor": "#0054A6"})
- Columns: Clerk File #, Account, Certificate Number, Reference (parcel ID),
  Sales Date, Status, Opening Bid Amount, Legal Description,
  Surplus Balance, Property Address
- Dedup key: listing_events.mls_number = Clerk File #
- signal_tier=1, signal_type='tax_deed', source='escambia_clerk_taxsale'
- Windows Python 3.13: use %b not %B for month parsing (%B fails silently)
- Historical backfill complete: 5,730 records, 2019-01-07 – 2026-12-02

Run commands:
  python real_invest_fl/ingest/run_taxdeed.py --upcoming
  python real_invest_fl/ingest/run_taxdeed.py --historical
  python real_invest_fl/ingest/run_taxdeed.py --date 5/6/2026

### zillow_parser.py (staging)
- Accepts mixed listing types. listing_type and signal_type derived from
  specs line suffix — not hardcoded.
- _extract_street() uses strip_unit=False
- _normalize_address() uses strip_unit=True (dedup key only)
- _extract_zip() anchors to end of string: \b(\d{5})\s*$
- Wired through listing_matcher.py lookup_parcel_by_address()

## data_source_status Sources (v0.12)

Supported source strings:
  escambia_clerk_taxsale
  auction_com
  zillow_foreclosure
  escambia_landmarkweb
  escambia_realforeclose
  escambia_realtaxdeed

Composite PK: (source, county_fips)
Shared upsert helper: real_invest_fl/ingest/source_status.py

## Source Investigation Results (2026-04-28)

### Tax Delinquency
- Escambia Tax Collector delinquent page: navigation hub only, no data.
- escambia.county-taxes.com: landing page only, dead end.
- LienHub advertised list: high-value bulk list, available after 2026-05-05.
  URL: https://lienhub.com/county/escambia/certsale/main
       ?unique_id=41C54840429511F1A2F69948A6B8334F
       &use_this=print_advertised_list
- LienExpress: redirects to LienHub — not a standalone source.

### Government Auction
- Escambia County Surplus Auctions: zero listings at investigation date. Monitor.
  https://myescambia.com/our-services/property-sales/surplus-property-auction
- HUD Home Store: zero Escambia listings at investigation date. Monitor.
  https://www.hudhomestore.gov/searchresult?citystate=FL

### Robots / Access Notes
- Tier 1 sources (RealForeclose, RealTaxDeed, LandmarkWeb): robots.txt blocks
  live scraping. File-drop parsers are the approved pattern.
- public.escambiaclerk.com: generic crawlers permitted; ClaudeBot blocked by name.
  Behind Cloudflare — Playwright required.
  
### Tier 3 — Free Listing Sources
- Craigslist FSBO: technically feasible, messy data, deferred indefinitely.
- Facebook Marketplace: login required, TOS risk, manual-only. No scraper path.

### Tier 4 — Commercial Platforms
- Zillow: good data quality, anti-scraping posture is the obstacle.
  RapidAPI wrapper is the approved POC approach. Deferred to Tier 4.
- Redfin, Realtor.com, Homes.com: deferred — no investigation conducted yet.

