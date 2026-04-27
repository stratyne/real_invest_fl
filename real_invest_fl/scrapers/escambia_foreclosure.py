"""
real_invest_fl/scrapers/escambia_foreclosure.py
-------------------------------------------------
Tier 1 scraper — Escambia County mortgage foreclosure sales.

Source: https://escambia.realforeclose.com
Operator: RealForeclose (contracted by Escambia County Clerk of Courts)
Data type: Active mortgage foreclosure auction listings
Signal tier: 1 (government distress record — highest motivation signal)
Signal type: foreclosure_sale

This is a public government portal. No authentication is required.
Listings are properties where a lender has filed suit for default and
the court has scheduled a foreclosure auction. Owners of these properties
are under documented legal and financial pressure to sell.

Scraping approach:
    - Uses requests + BeautifulSoup (no JavaScript rendering required
      for the listing table on the search results page)
    - Playwright fallback is noted but not implemented in v1 —
      enable if the site adds JS-rendered content
    - One request per page of results with random delay between pages
    - robots.txt checked before first request

Page structure (as of 2026-04):
    The main auction listing table is at:
    https://escambia.realforeclose.com/index.cfm?zaction=AUCTION&Zmethod=PREVIEW
    Table rows contain: case number, parcel ID, address, auction date, opening bid

ETHICAL / LEGAL NOTICE:
    This scraper targets a public government portal operated by the
    Escambia County Clerk of Courts. The data is explicitly public
    under Florida Statutes Chapter 119. Rate limiting and robots.txt
    compliance are enforced. Do not increase request frequency beyond
    the defaults without legal review.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime

import requests
from bs4 import BeautifulSoup

from real_invest_fl.scrapers.base_scraper import BaseScraper, ScrapedListing, PENSTOCK_UA

logger = logging.getLogger(__name__)

# ── source configuration ──────────────────────────────────────────────────────

BASE_URL      = "https://escambia.realforeclose.com"
LISTING_URL   = f"{BASE_URL}/index.cfm"
COUNTY_FIPS   = "12033"

# Default request parameters for the listing search
DEFAULT_PARAMS = {
    "zaction":  "AUCTION",
    "Zmethod":  "PREVIEW",
    "STATUS":   "A",     # A = Active auctions only
    "myState":  "FL",
}

# Page size is controlled by the site — typically 25 per page
MAX_PAGES = 20   # Safety cap — Escambia rarely has more than 5-10 pages


class EscambiaForeclosureScraper(BaseScraper):
    """
    Scrapes active mortgage foreclosure auction listings from
    escambia.realforeclose.com and returns a list of ScrapedListing records.

    Each listing represents a property with an active court-ordered
    foreclosure auction scheduled — a Tier 1 motivation signal.
    """

    SOURCE_NAME = "escambia_realforeclose"
    SIGNAL_TIER = 1
    SIGNAL_TYPE = "foreclosure_sale"
    ENABLED     = True

    # Conservative delay for a government portal
    delay_range = (3.0, 6.0)

    def scrape(self) -> list[ScrapedListing]:
        """
        Scrape all active foreclosure auction listings from escambia.realforeclose.com.
        Paginates through all result pages. Returns a list of ScrapedListing records.
        """
        listings: list[ScrapedListing] = []

        session = requests.Session()
        session.headers.update({
            "User-Agent": PENSTOCK_UA,
            "Accept-Language": "en-US,en;q=0.9",
        })

        for page_num in range(1, MAX_PAGES + 1):
            params = {**DEFAULT_PARAMS, "StartIndex": (page_num - 1) * 25}
            url    = LISTING_URL + "?" + "&".join(f"{k}={v}" for k, v in params.items())

            response = self._safe_fetch(session.get, url, timeout=20)
            if response is None:
                logger.warning("No response for page %d — stopping pagination", page_num)
                break

            if response.status_code != 200:
                logger.warning(
                    "HTTP %d on page %d — stopping pagination",
                    response.status_code, page_num,
                )
                break

            page_listings, has_more = self._parse_listing_page(response.text, page_num)
            listings.extend(page_listings)

            logger.info(
                "Page %d — parsed %d listings (total so far: %d)",
                page_num, len(page_listings), len(listings),
            )

            if not has_more or not page_listings:
                logger.info("No more pages after page %d", page_num)
                break

        logger.info(
            "EscambiaForeclosureScraper complete — %d total listings", len(listings)
        )
        return listings

    def _parse_listing_page(
        self,
        html: str,
        page_num: int,
    ) -> tuple[list[ScrapedListing], bool]:
        """
        Parse one page of foreclosure auction results.

        Returns:
            (listings, has_more)
            listings  — list of ScrapedListing records parsed from this page
            has_more  — True if a next page likely exists
        """
        soup     = BeautifulSoup(html, "html.parser")
        listings: list[ScrapedListing] = []

        # The listing table on realforeclose.com uses CSS class 'AUCTION_ITEM'
        # for each property card/row. If the structure changes, update here.
        auction_items = soup.find_all("div", class_="AUCTION_ITEM")

        if not auction_items:
            # Try table row fallback — some RealForeclose instances use <tr>
            auction_items = soup.find_all("tr", class_=re.compile(r"(?i)auction"))

        if not auction_items:
            logger.debug(
                "No AUCTION_ITEM elements found on page %d — "
                "page may be empty or structure changed",
                page_num,
            )
            return [], False

        for item in auction_items:
            listing = self._parse_single_item(item)
            if listing is not None:
                listings.append(listing)

        # has_more: if this page returned a full set of items, there may be more
        has_more = len(auction_items) >= 25
        return listings, has_more

    def _parse_single_item(self, item) -> ScrapedListing | None:
        """
        Parse a single auction item element into a ScrapedListing.
        Returns None if the item cannot be parsed into a usable record.
        """
        try:
            text_content = item.get_text(separator=" ", strip=True)

            # ── Address extraction ─────────────────────────────────────── #
            # RealForeclose typically shows address in a <div> or <td>
            # with class containing 'ADDR' or as labeled text
            raw_address = ""
            raw_zip     = ""

            addr_el = (
                item.find(class_=re.compile(r"(?i)addr"))
                or item.find("td", string=re.compile(r"\d+\s+\w+"))
            )
            if addr_el:
                raw_address = addr_el.get_text(strip=True)

            # Extract ZIP from address if present
            zip_match = re.search(r"\b(3250\d|3251[0-9]|3252[0-9]|3253[0-9])\b", text_content)
            if zip_match:
                raw_zip = zip_match.group(0)

            if not raw_address:
                logger.debug("Could not extract address from auction item — skipping")
                return None

            # ── Case number / listing URL ──────────────────────────────── #
            case_number = ""
            listing_url = ""

            case_el = item.find(class_=re.compile(r"(?i)case"))
            if case_el:
                case_number = case_el.get_text(strip=True)

            link_el = item.find("a", href=True)
            if link_el:
                href = link_el["href"]
                listing_url = (
                    href if href.startswith("http")
                    else f"{BASE_URL}/{href.lstrip('/')}"
                )

            # ── Opening bid (list price proxy) ─────────────────────────── #
            list_price: int | None = None
            bid_match = re.search(
                r"(?i)(?:opening\s+bid|minimum\s+bid|opening\s+amount)[:\s]*\$?([\d,]+)",
                text_content,
            )
            if bid_match:
                try:
                    list_price = int(bid_match.group(1).replace(",", ""))
                except ValueError:
                    pass

            # ── Auction date ───────────────────────────────────────────── #
            list_date: date | None = None
            date_match = re.search(
                r"\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})\b", text_content
            )
            if date_match:
                try:
                    list_date = date(
                        int(date_match.group(3)),
                        int(date_match.group(1)),
                        int(date_match.group(2)),
                    )
                except ValueError:
                    pass

            return ScrapedListing(
                raw_address      = raw_address,
                raw_city         = "Pensacola",
                raw_state        = "FL",
                raw_zip          = raw_zip,
                listing_url      = listing_url or None,
                list_price       = list_price,
                list_date        = list_date,
                raw_listing_json = {
                    "case_number":    case_number,
                    "raw_text":       text_content[:500],
                    "source_page_ua": PENSTOCK_UA,
                },
            )

        except Exception as exc:
            logger.warning(
                "Failed to parse auction item: %s", exc, exc_info=True
            )
            return None
