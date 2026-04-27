"""
real_invest_fl/scrapers/
-------------------------
Phase 2 scraper framework.

Each module in this package is an independent source scraper.
All scrapers inherit from BaseScraper and produce standardized
ScrapedListing records that feed into listing_matcher.py.

Source modules — enabled flag controls daily scheduler inclusion:

Tier 1 — Government distress records (highest signal, lowest risk):
    escambia_foreclosure.py   — Escambia County mortgage foreclosure sales
    escambia_tax_deed.py      — Escambia County tax deed auctions
    escambia_lis_pendens.py   — Escambia County lis pendens filings (deferred)

Tier 2 — Government auction / bulk public data:
    hud_homes.py              — HUD Home Store listings (deferred)
    escambia_surplus.py       — Escambia County surplus property auctions (deferred)

Tier 3 — Commercial listing platforms / FSBO:
    craigslist_fsbo.py        — Craigslist Pensacola housing (deferred)
    auction_com.py            — Auction.com Escambia County (deferred)
    zillow.py                 — Zillow via paid API intermediary (deferred)
"""
