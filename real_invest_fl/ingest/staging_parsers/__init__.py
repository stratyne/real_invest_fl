"""
real_invest_fl/ingest/staging_parsers/
---------------------------------------
File-drop parsers for manually retrieved government data sources.

Each parser reads files from a watched staging subdirectory,
resolves parcels against the MQI, and writes listing_events records.

Parsers:
    lis_pendens_parser.py   — LandmarkWeb Excel export (weekly drop)
    foreclosure_parser.py   — RealForeclose manual CSV (weekly drop)
    tax_deed_parser.py      — RealTaxDeed manual CSV (monthly drop)

All parsers are idempotent — re-processing the same file produces
no duplicate records. Deduplication key is CFN (lis pendens) or
case_number (foreclosure/tax deed).
"""
