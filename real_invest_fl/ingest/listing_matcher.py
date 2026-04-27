"""
real_invest_fl/ingest/listing_matcher.py
------------------------------------------
Phase 2 — Listing feed → parcel lookup → listing_events.

Orchestrates the full daily scrape-and-match cycle:

    1. Load all enabled scrapers from real_invest_fl.scrapers.*
    2. Run each scraper — collect ScrapedListing records
    3. Normalize each scraped address via address_to_parcel()
    4. Look up the matched parcel in the properties table
    5. Verify the parcel is MQI-qualified
    6. Compute derived financial fields (price_per_sqft, arv_spread)
    7. Insert a ListingEvent record for each matched, qualified parcel
    8. Log run summary via IngestRunContext

Address matching strategy:
    Primary:   Exact match on normalized phy_addr1 + phy_zipcd
    Secondary: Fuzzy match using rapidfuzz on street address
               (threshold configurable via FUZZY_MATCH_THRESHOLD)
    Fallback:  Log as unmatched — never insert a record with no parcel_id

Usage:
    python -m real_invest_fl.ingest.listing_matcher [--dry-run] [--source NAME]

Options:
    --dry-run       Scrape and match but do not write to database.
    --source NAME   Run only the named scraper (by SOURCE_NAME). Default: all.

ETHICAL / LEGAL NOTICE:
    This module coordinates scrapers that target public sources only.
    Each scraper is responsible for its own robots.txt compliance and
    rate limiting. This module adds no additional HTTP requests.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import logging
import pkgutil
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# ── path bootstrap ────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import settings                          # noqa: E402
from real_invest_fl.db.session import AsyncSessionLocal       # noqa: E402
from real_invest_fl.db.models.listing_event import ListingEvent  # noqa: E402
from real_invest_fl.scrapers.base_scraper import BaseScraper, ScrapedListing  # noqa: E402
from real_invest_fl.utils.parcel_id import normalize_parcel_id   # noqa: E402
from real_invest_fl.utils.text import clean_text                 # noqa: E402

if TYPE_CHECKING:
    pass

# ── logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("listing_matcher")

# ── constants ─────────────────────────────────────────────────────────────────
COUNTY_FIPS   = "12033"   # Escambia County — Phase 1 POC
FUZZY_MATCH_THRESHOLD = 88  # rapidfuzz score threshold (0-100)


# ── scraper discovery ─────────────────────────────────────────────────────────

def _discover_scrapers() -> list[type[BaseScraper]]:
    """
    Auto-discover all BaseScraper subclasses in real_invest_fl.scrapers.
    Returns a list of scraper classes (not instances).
    Skips any module that fails to import — logs the error and continues.
    """
    import real_invest_fl.scrapers as scrapers_pkg

    scraper_classes: list[type[BaseScraper]] = []

    for module_info in pkgutil.iter_modules(scrapers_pkg.__path__):
        module_name = f"real_invest_fl.scrapers.{module_info.name}"
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            logger.error("Failed to import scraper module %s: %s", module_name, exc)
            continue

        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseScraper)
                and attr is not BaseScraper
            ):
                scraper_classes.append(attr)
                logger.debug("Discovered scraper: %s", attr.__name__)

    logger.info("Discovered %d scraper class(es)", len(scraper_classes))
    return scraper_classes


# ── address normalization ─────────────────────────────────────────────────────

def _normalize_address(addr: str) -> str:
    """
    Normalize a raw scraped address for comparison against phy_addr1.
    Strips unit numbers, collapses whitespace, upper-cases.
    This is a best-effort normalization — the fuzzy matcher handles
    residual differences.
    """
    import re
    addr = clean_text(addr).upper()
    # Strip common unit designators
    addr = re.sub(
        r"\b(APT|UNIT|STE|SUITE|#)\s*[\w-]+\b", "", addr
    ).strip()
    # Collapse internal whitespace again after stripping
    addr = re.sub(r"\s+", " ", addr).strip()
    return addr


# ── parcel lookup ─────────────────────────────────────────────────────────────

async def _build_address_index(session: AsyncSession) -> dict[str, dict]:
    """
    Load all MQI-qualified parcels into an in-memory address index.
    Key: normalized "ADDRESS|ZIPCD" string
    Value: dict with parcel_id, county_fips, jv, arv_estimate,
           tot_lvg_area, filter_profile_id

    Loading the full index once per run is faster than per-listing
    DB lookups for the expected volume of scraped listings.
    For large multi-county deployments this should be replaced with
    a DB lookup per listing — see TODO below.
    """
    logger.info("Building address index from MQI-qualified parcels...")
    result = await session.execute(text("""
        SELECT
            parcel_id,
            county_fips,
            phy_addr1,
            phy_zipcd,
            jv,
            arv_estimate,
            tot_lvg_area
        FROM properties
        WHERE mqi_qualified = true
        AND county_fips = :county_fips
    """), {"county_fips": COUNTY_FIPS})

    rows = result.fetchall()
    index: dict[str, dict] = {}

    for row in rows:
        if not row.phy_addr1:
            continue
        norm_addr = _normalize_address(row.phy_addr1)
        zip_cd    = (row.phy_zipcd or "").strip()
        key       = f"{norm_addr}|{zip_cd}"
        index[key] = {
            "parcel_id":    row.parcel_id,
            "county_fips":  row.county_fips,
            "jv":           row.jv,
            "arv_estimate": row.arv_estimate,
            "tot_lvg_area": row.tot_lvg_area,
        }

    logger.info("Address index built — %d entries", len(index))
    return index


def _lookup_parcel(
    listing: ScrapedListing,
    index: dict[str, dict],
) -> dict | None:
    """
    Attempt to match a ScrapedListing to a parcel in the address index.

    Strategy:
        1. Exact match on normalized address + zip
        2. Fuzzy match on address only (zip ignored) if exact fails
           and rapidfuzz is available
        3. Return None if no match found above threshold
    """
    norm_addr = _normalize_address(listing.raw_address)
    zip_cd    = (listing.raw_zip or "").strip()
    exact_key = f"{norm_addr}|{zip_cd}"

    # Exact match
    if exact_key in index:
        return index[exact_key]

    # Fuzzy match — requires rapidfuzz
    try:
        from rapidfuzz import process as fuzz_process, fuzz
        # Search only on the address portion of the key
        choices = {k: v for k, v in index.items() if k.endswith(f"|{zip_cd}") or not zip_cd}
        if not choices:
            choices = index  # Fall back to all parcels if zip yields nothing

        match_result = fuzz_process.extractOne(
            norm_addr,
            {k: k.split("|")[0] for k in choices},
            scorer=fuzz.token_sort_ratio,
            score_cutoff=FUZZY_MATCH_THRESHOLD,
        )
        if match_result:
            matched_key = match_result[2]   # extractOne returns (match, score, key)
            return choices.get(matched_key)

    except ImportError:
        logger.debug("rapidfuzz not installed — fuzzy matching unavailable")

    return None


# ── financial derivation ──────────────────────────────────────────────────────

def _derive_financials(
    listing: ScrapedListing,
    parcel: dict,
) -> dict:
    """
    Compute derived financial fields for the listing_events record.
    Returns a dict of fields to merge into the insert payload.
    """
    arv_estimate  = parcel.get("arv_estimate") or parcel.get("jv")
    list_price    = listing.list_price
    tot_lvg_area  = parcel.get("tot_lvg_area")

    price_per_sqft: float | None = None
    if list_price and tot_lvg_area and tot_lvg_area > 0:
        price_per_sqft = round(list_price / tot_lvg_area, 2)

    arv_spread: int | None = None
    if arv_estimate and list_price and list_price > 0:
        arv_spread = arv_estimate - list_price

    return {
        "arv_estimate":  arv_estimate,
        "arv_source":    "JV",       # Phase 1 proxy — updated to SDF_COMPS in Phase 3
        "price_per_sqft": price_per_sqft,
        "arv_spread":    arv_spread,
    }


# ── active filter profile lookup ─────────────────────────────────────────────

async def _get_active_filter_profile(session: AsyncSession) -> dict | None:
    """Load the active filter profile for Escambia County."""
    result = await session.execute(text("""
        SELECT id, filter_criteria
        FROM filter_profiles
        WHERE county_fips = :county_fips
        AND active = true
        LIMIT 1
    """), {"county_fips": COUNTY_FIPS})
    row = result.fetchone()
    if row:
        return {"id": row.id, "criteria": row.filter_criteria}
    return None


# ── core matching pipeline ────────────────────────────────────────────────────

async def run_matching_cycle(
    dry_run: bool,
    source_filter: str | None,
) -> None:
    """
    Full scrape-and-match cycle.

    Steps:
        1. Discover and instantiate enabled scrapers
        2. Run each scraper, collect ScrapedListing records
        3. Build MQI address index from DB
        4. Load active filter profile
        5. For each listing: lookup parcel, derive financials, insert event
        6. Log summary
    """
    t_start = time.time()

    # ── Step 1 — Discover scrapers ─────────────────────────────────────── #
    scraper_classes = _discover_scrapers()

    if source_filter:
        scraper_classes = [
            cls for cls in scraper_classes
            if cls.SOURCE_NAME == source_filter
        ]
        if not scraper_classes:
            logger.error(
                "No scraper found with SOURCE_NAME='%s'", source_filter
            )
            return

    # ── Step 2 — Run scrapers ──────────────────────────────────────────── #
    all_listings: list[ScrapedListing] = []
    scrapers_run = 0
    scrapers_skipped = 0

    for cls in scraper_classes:
        scraper = cls()
        if not scraper.ENABLED:
            scrapers_skipped += 1
            continue
        scrapers_run += 1
        listings = scraper.run()
        all_listings.extend(listings)
        logger.info(
            "Scraper '%s' returned %d listings",
            cls.SOURCE_NAME, len(listings),
        )

    logger.info(
        "Scrape phase complete | scrapers_run=%d scrapers_skipped=%d "
        "total_listings=%d",
        scrapers_run, scrapers_skipped, len(all_listings),
    )

    if not all_listings:
        logger.info("No listings to match — exiting.")
        return

    # ── Steps 3-7 — Match and insert ──────────────────────────────────── #
    async with AsyncSessionLocal() as session:
        address_index   = await _build_address_index(session)
        filter_profile  = await _get_active_filter_profile(session)

        if not filter_profile:
            logger.warning(
                "No active filter profile found for county_fips=%s — "
                "filter_profile_id will be NULL on inserted records",
                COUNTY_FIPS,
            )

        matched      = 0
        unmatched    = 0
        inserted     = 0
        dry_run_would_insert = 0

        for listing in all_listings:
            # Step 4 — Parcel lookup
            parcel = _lookup_parcel(listing, address_index)
            if parcel is None:
                unmatched += 1
                logger.debug(
                    "No parcel match | address='%s %s'",
                    listing.raw_address, listing.raw_zip,
                )
                continue

            matched += 1

            # Step 5 — Derive financials
            financials = _derive_financials(listing, parcel)

            # Step 6 — Build ListingEvent payload
            event_data = {
                "county_fips":          parcel["county_fips"],
                "parcel_id":            parcel["parcel_id"],
                "signal_tier":          listing.signal_tier,
                "signal_type":          listing.signal_type,
                "listing_type":         listing.listing_type,
                "list_price":           listing.list_price,
                "list_date":            listing.list_date,
                "expiry_date":          listing.expiry_date,
                "days_on_market":       listing.days_on_market,
                "source":               listing.source,
                "listing_url":          listing.listing_url,
                "listing_agent_name":   listing.listing_agent_name,
                "listing_agent_email":  listing.listing_agent_email,
                "listing_agent_phone":  listing.listing_agent_phone,
                "mls_number":           listing.mls_number,
                "price_per_sqft":       financials["price_per_sqft"],
                "arv_estimate":         financials["arv_estimate"],
                "arv_source":           financials["arv_source"],
                "arv_spread":           financials["arv_spread"],
                "filter_profile_id":    filter_profile["id"] if filter_profile else None,
                "workflow_status":      "NEW",
                "raw_listing_json":     listing.raw_listing_json,
                "scraped_at":           listing.scraped_at,
            }

            if dry_run:
                dry_run_would_insert += 1
                logger.info(
                    "[DRY-RUN] Would insert | parcel_id=%s source=%s "
                    "signal_type=%s list_price=%s arv_spread=%s",
                    parcel["parcel_id"],
                    listing.source,
                    listing.signal_type,
                    listing.list_price,
                    financials["arv_spread"],
                )
                continue

            # Step 7 — Insert ListingEvent
            event = ListingEvent(**event_data)
            session.add(event)
            inserted += 1

        if not dry_run and inserted > 0:
            await session.commit()
            logger.info("Committed %d new listing_events records", inserted)

    elapsed = time.time() - t_start
    if dry_run:
        logger.info(
            "[DRY-RUN] Matching cycle complete | scraped=%d matched=%d "
            "unmatched=%d would_insert=%d duration=%.1fs",
            len(all_listings), matched, unmatched,
            dry_run_would_insert, elapsed,
        )
    else:
        logger.info(
            "Matching cycle complete | scraped=%d matched=%d "
            "unmatched=%d inserted=%d duration=%.1fs",
            len(all_listings), matched, unmatched, inserted, elapsed,
        )


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the Phase 2 scrape-and-match cycle."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Scrape and match but do not write to the database.",
    )
    parser.add_argument(
        "--source", type=str, default=None,
        help="Run only the named scraper by SOURCE_NAME. Default: all enabled.",
    )
    args = parser.parse_args()

    asyncio.run(run_matching_cycle(
        dry_run=args.dry_run,
        source_filter=args.source,
    ))


if __name__ == "__main__":
    main()
