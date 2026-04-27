"""
real_invest_fl/scrapers/base_scraper.py
-----------------------------------------
Abstract base class for all Phase 2 source scrapers.

Every source module must:
    1. Inherit from BaseScraper
    2. Set class attributes: SOURCE_NAME, SIGNAL_TIER, SIGNAL_TYPE, ENABLED
    3. Implement scrape() -> list[ScrapedListing]

The framework (listing_matcher.py) calls scrape() on every enabled
scraper, then passes each ScrapedListing through address normalization,
parcel lookup, filter evaluation, and listing_events insertion.

ETHICAL / LEGAL NOTICE:
    All scrapers must:
    - Call can_fetch() before any HTTP request and abort if disallowed
    - Respect random delays between requests (min 2s, default 3-5s)
    - Identify themselves via a descriptive User-Agent string
    - Never hammer a single endpoint in rapid succession
    - Comply with each source site's Terms of Service
    The operator bears full responsibility for compliance with each
    source's ToS. Government public records portals are the preferred
    source precisely because they are explicitly public and carry no
    scraping restrictions.
"""
from __future__ import annotations

import logging
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from real_invest_fl.utils.robots import can_fetch

logger = logging.getLogger(__name__)

# User-Agent used for all HTTP requests across all scrapers.
# Identifies the bot honestly — do not spoof a browser agent.
PENSTOCK_UA = (
    "Penstock/1.0 (real estate investment research; "
    "public records only; contact: ops@stratyne.com)"
)

# Default delay range between requests in seconds (min, max)
DEFAULT_DELAY_MIN = 2.0
DEFAULT_DELAY_MAX = 5.0


@dataclass
class ScrapedListing:
    """
    Standardized listing record produced by every scraper.

    Required fields: raw_address, source.
    All other fields are optional — scrapers populate what is available.
    The matcher resolves raw_address to parcel_id before DB insertion.
    """
    # Address — required for parcel lookup
    raw_address:     str = ""            # Full address string as scraped
    raw_city:        str = ""
    raw_state:       str = "FL"
    raw_zip:         str = ""

    # Signal classification — set by scraper from class attributes
    signal_tier:     int | None = None
    signal_type:     str | None = None

    # Listing metadata — populate what is available
    listing_type:    str | None = None   # MLS status if known
    list_price:      int | None = None
    list_date:       date | None = None
    expiry_date:     date | None = None
    days_on_market:  int | None = None
    listing_url:     str | None = None
    listing_agent_name:  str | None = None
    listing_agent_email: str | None = None
    listing_agent_phone: str | None = None
    mls_number:      str | None = None
    source:          str | None = None   # Set from SOURCE_NAME by base class

    # Raw captured data — store everything scraped for auditability
    raw_listing_json: dict = field(default_factory=dict)

    # Scrape timestamp — set automatically by base class post-scrape
    scraped_at:      datetime | None = None


class BaseScraper(ABC):
    """
    Abstract base class for all Penstock source scrapers.

    Subclasses must define:
        SOURCE_NAME  : str   — human-readable source name stored in listing_events.source
        SIGNAL_TIER  : int   — 1, 2, or 3 per the tier definitions
        SIGNAL_TYPE  : str   — semantic event type stored in signal_type
        ENABLED      : bool  — False disables the scraper in the daily run

    Subclasses must implement:
        scrape() -> list[ScrapedListing]

    Subclasses may override:
        delay_range  : tuple[float, float] — (min, max) seconds between requests
    """

    SOURCE_NAME:  str  = "unknown"
    SIGNAL_TIER:  int  = 3
    SIGNAL_TYPE:  str  = "unknown"
    ENABLED:      bool = False

    delay_range: tuple[float, float] = (DEFAULT_DELAY_MIN, DEFAULT_DELAY_MAX)

    def __init__(self) -> None:
        self.logger = logging.getLogger(
            f"scraper.{self.__class__.__name__}"
        )
        self.logger.info(
            "Scraper initialized | source=%s tier=%d type=%s enabled=%s",
            self.SOURCE_NAME, self.SIGNAL_TIER, self.SIGNAL_TYPE, self.ENABLED,
        )

    # ------------------------------------------------------------------ #
    # Public interface — called by listing_matcher.py                      #
    # ------------------------------------------------------------------ #

    def run(self) -> list[ScrapedListing]:
        """
        Entry point called by the framework.
        Checks ENABLED, calls scrape(), stamps scraped_at, returns results.
        Never raises — logs exceptions and returns empty list on failure.
        """
        if not self.ENABLED:
            self.logger.info(
                "Scraper disabled — skipping | source=%s", self.SOURCE_NAME
            )
            return []

        self.logger.info("Scrape starting | source=%s", self.SOURCE_NAME)
        t_start = time.time()

        try:
            results = self.scrape()
        except Exception as exc:
            self.logger.error(
                "Scrape failed | source=%s | %s",
                self.SOURCE_NAME, exc, exc_info=True,
            )
            return []

        # Stamp all results with source name, signal fields, and scraped_at
        now = datetime.utcnow()
        for listing in results:
            listing.source      = self.SOURCE_NAME
            listing.signal_tier = self.SIGNAL_TIER
            listing.signal_type = self.SIGNAL_TYPE
            listing.scraped_at  = now

        elapsed = time.time() - t_start
        self.logger.info(
            "Scrape complete | source=%s | results=%d | duration=%.1fs",
            self.SOURCE_NAME, len(results), elapsed,
        )
        return results

    # ------------------------------------------------------------------ #
    # Abstract — must be implemented by each source module                 #
    # ------------------------------------------------------------------ #

    @abstractmethod
    def scrape(self) -> list[ScrapedListing]:
        """
        Perform the actual scrape and return a list of ScrapedListing records.
        Do not set source, signal_tier, signal_type, or scraped_at here —
        run() handles those automatically after scrape() returns.
        """
        ...

    # ------------------------------------------------------------------ #
    # Protected helpers — available to all subclasses                      #
    # ------------------------------------------------------------------ #

    def _check_robots(self, url: str) -> bool:
        """
        Return True if robots.txt permits fetching this URL.
        Logs a warning and returns False if disallowed.
        Always call this before making any HTTP request.
        """
        if not can_fetch(url, user_agent=PENSTOCK_UA):
            self.logger.warning(
                "robots.txt disallows fetch | source=%s url=%s",
                self.SOURCE_NAME, url,
            )
            return False
        return True

    def _delay(self) -> None:
        """
        Sleep for a random duration within delay_range.
        Call between every HTTP request.
        """
        delay = random.uniform(*self.delay_range)
        self.logger.debug("Delaying %.2fs before next request", delay)
        time.sleep(delay)

    def _safe_fetch(self, fetch_fn: Any, url: str, *args, **kwargs) -> Any | None:
        """
        Wrapper that checks robots.txt, delays, then calls fetch_fn(url, ...).
        Returns None if robots.txt disallows or fetch_fn raises.

        Args:
            fetch_fn : callable — the actual fetch function (requests.get,
                       page.goto, etc.)
            url      : the URL being fetched
            *args, **kwargs passed through to fetch_fn
        """
        if not self._check_robots(url):
            return None
        self._delay()
        try:
            return fetch_fn(url, *args, **kwargs)
        except Exception as exc:
            self.logger.error(
                "Fetch error | source=%s url=%s | %s",
                self.SOURCE_NAME, url, exc, exc_info=True,
            )
            return None
