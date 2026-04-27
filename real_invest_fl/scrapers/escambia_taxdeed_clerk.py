"""
Escambia County Clerk – Tax Deed Sale scraper.

Fetches sale dates from:
    https://public.escambiaclerk.com/taxsale/taxsaledates.asp
Fetches per-date property tables from:
    https://public.escambiaclerk.com/taxsale/taxsaleMobile.asp?saledate=M/D/YYYY

Transport: Playwright (headless Chromium).
  - requests is blocked by Cloudflare (403) regardless of User-Agent.
  - Both target pages require JavaScript execution to render the table;
    wait_until='domcontentloaded' fires before the table is built.
    We wait for a CSS selector that only exists post-render instead.
  - The saledate query parameter contains literal forward slashes and must
    NOT be percent-encoded; Playwright goto() with a pre-built URL string
    preserves them correctly.
  - A single persistent BrowserContext is reused across all pages so that
    session cookies set by the dates page are available to detail pages.

For each scraped row:
  - Normalises the Reference field (parcel ID) and confirms the parcel exists
    in properties (county_fips='12033').  Rows with no match are skipped and
    counted.
  - Inserts into listing_events using listing_events.parcel_id (VARCHAR, the
    normalised Reference string directly) — there is no property_id FK column.
  - Deduplicates on mls_number via WHERE NOT EXISTS — there is no unique
    constraint on listing_events.mls_number so ON CONFLICT cannot be used.

Schema facts confirmed from \\d listing_events:
    parcel_id        VARCHAR(30) NOT NULL
    mls_number       VARCHAR(50)           no unique constraint
    signal_tier      INTEGER
    signal_type      VARCHAR(50)
    list_price       INTEGER
    list_date        DATE
    workflow_status  VARCHAR(30) NOT NULL
    county_fips      VARCHAR(5)  NOT NULL
    notes            TEXT
    raw_listing_json JSONB
    scraped_at       TIMESTAMPTZ
    created_at       TIMESTAMPTZ NOT NULL  default now()
    updated_at       TIMESTAMPTZ NOT NULL  default now()
"""

from __future__ import annotations

import json
import logging
import random
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from sqlalchemy import create_engine, text

# ---------------------------------------------------------------------------
# ROOT / settings bootstrap
# File:  real_invest_fl/scrapers/escambia_taxdeed_clerk.py
#   .parent  ->  real_invest_fl/scrapers/
#   .parent  ->  real_invest_fl/
#   .parent  ->  project root                    (same depth as gis_ingest.py)
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import settings  # noqa: E402

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("escambia_taxdeed_clerk")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DATES_URL   = "https://public.escambiaclerk.com/taxsale/taxsaledates.asp"
DETAIL_URL  = "https://public.escambiaclerk.com/taxsale/taxsaleMobile.asp"
COUNTY_FIPS = "12033"
SIGNAL_TIER = 1
SIGNAL_TYPE = "tax_deed"
SOURCE      = "escambia_clerk_taxsale"
BATCH_SIZE  = 500

# Selector that only exists in the DOM after the table has fully rendered.
# Targets the first data cell in the Clerk File # column.
TABLE_READY_SELECTOR = "table tr:nth-child(2) td:nth-child(2)"

# Maximum time (ms) to wait for the table selector before giving up.
TABLE_WAIT_TIMEOUT_MS = 20_000

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _sleep() -> None:
    """Random 3-6 second polite delay between page navigations."""
    delay = random.uniform(3.0, 6.0)
    logger.debug("Sleeping %.2fs", delay)
    time.sleep(delay)


def _normalize_parcel(raw: str) -> str:
    """Strip all non-alphanumeric characters and uppercase.

    Applied identically to the scraped Reference field (Python-side) and
    to properties.parcel_id in SQL (via REGEXP_REPLACE) so formatting
    differences such as dashes, spaces, and dots do not break the join.
    """
    return re.sub(r"[^A-Z0-9]", "", raw.upper())


def _parse_opening_bid(raw: str) -> Optional[int]:
    """Parse Opening Bid Amount to integer dollars (cents truncated).

    Live examples: '**$1,909.61', '**$14,670.89', '$8,832.84'
    Strips asterisks, dollar signs, commas, and whitespace.
    Returns None if the field is blank or unparseable.
    """
    cleaned = re.sub(r"[*$,\s]", "", raw)
    if not cleaned:
        return None
    try:
        return int(float(cleaned))
    except (ValueError, TypeError):
        logger.warning("Could not parse opening bid: %r", raw)
        return None


def _parse_sale_date(raw: str) -> Optional[date]:
    """Parse Sales Date column to a Python date.

    The live page delivers abbreviated month names: 'May  6 2026', 'Nov 4 2026'.
    %b matches abbreviated months (Jan, Feb, ... Nov, Dec).
    %B matches full month names (January, February, ...) — never used here.
    Collapses multiple spaces before parsing, then zero-pads the day token
    as a fallback for single-digit days on Windows strptime.
    """
    raw = re.sub(r"\s+", " ", raw.strip())

    for fmt in ("%b %d %Y", "%b %d, %Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue

    # Zero-pad the day token and retry — handles 'Nov 4 2026' -> 'Nov 04 2026'
    parts = raw.split(" ")
    if len(parts) == 3:
        try:
            parts[1] = parts[1].zfill(2)
            return datetime.strptime(" ".join(parts), "%b %d %Y").date()
        except ValueError:
            pass

    logger.warning("Could not parse sale date: %r", raw)
    return None


def _chunks(lst: list, size: int) -> Iterator[list]:
    """Yield successive fixed-size chunks from lst."""
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


# ---------------------------------------------------------------------------
# Date-list page
# ---------------------------------------------------------------------------

def fetch_all_dates(context) -> list[date]:
    """Fetch taxsaledates.asp and return every sale date in the bullet list.

    The page renders a flat <ul>; each <li> is a bare M/D/YYYY string.
    The first <li> ('Tax Deed Sales') is a section header and is skipped
    by the numeric regex.  Returns dates sorted ascending.
    """
    logger.info("Fetching sale date list from %s", DATES_URL)
    page = context.new_page()
    try:
        page.goto(DATES_URL, wait_until="domcontentloaded", timeout=30_000)
        # The dates list is server-rendered static HTML — no JS wait needed.
        page.wait_for_selector("ul li", timeout=10_000)
        html = page.content()
    finally:
        page.close()

    soup = BeautifulSoup(html, "html.parser")
    dates: list[date] = []
    for li in soup.find_all("li"):
        token = li.get_text(strip=True)
        if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", token):
            try:
                parsed = datetime.strptime(token, "%m/%d/%Y").date()
                dates.append(parsed)
            except ValueError:
                logger.warning("Unparseable date token in <li>: %r", token)

    logger.info("Found %d dates on the dates page", len(dates))
    return sorted(dates)


# ---------------------------------------------------------------------------
# Detail page parsing
# ---------------------------------------------------------------------------

# Maps lowercase header-text fragments to normalised field names.
# The leading blank 'View Image' column produces no match and is ignored.
_HEADER_MAP: dict[str, str] = {
    "clerk file #":       "clerk_file",
    "clerk file":         "clerk_file",
    "account":            "account",
    "certificate number": "certificate_number",
    "reference":          "reference",
    "sales date":         "sales_date",
    "status":             "status",
    "opening bid amount": "opening_bid_amount",
    "legal description":  "legal_description",
    "surplus balance":    "surplus_balance",
    "property address":   "property_address",
}


def _map_headers(cells: list) -> dict[int, str]:
    """Return {column_index: field_name} for every recognisable header cell."""
    mapping: dict[int, str] = {}
    for idx, cell in enumerate(cells):
        text_val = cell.get_text(separator=" ", strip=True).lower()
        for pattern, field in _HEADER_MAP.items():
            if pattern in text_val:
                mapping[idx] = field
                break
    return mapping


def parse_detail_page(html: str, sale_date_str: str) -> list[dict]:
    """Parse taxsaleMobile.asp HTML into a list of row dicts.

    The page uses a nested table layout:
      - Outer wrapper table (no distinguishing attrs) — contains title text
      - Data table (bgcolor='#0054A6') — nested inside outer, contains all rows
      - Footer table (width='100%') — contains the Count= line

    soup.find("table") returns the outer wrapper, not the data table, so we
    select the data table explicitly by its bgcolor attribute.

    Column mapping is header-text-driven so the leading 'View Image' <th>
    produces no match and is ignored. The trailing '.' <th> likewise produces
    no match. Multiline Legal Description cells are collapsed via
    get_text(separator=' ').
    """
    soup = BeautifulSoup(html, "html.parser")

    # Select the data table by its unique bgcolor attribute.
    # This is stable — it is hardcoded in the ASP source.
    table = soup.find("table", attrs={"bgcolor": "#0054A6"})
    if not table:
        logger.warning("No data table (bgcolor=#0054A6) found for sale date %s", sale_date_str)
        return []

    all_rows = table.find_all("tr")
    if not all_rows:
        logger.warning("Empty data table for sale date %s", sale_date_str)
        return []

    header_cells = all_rows[0].find_all(["th", "td"])
    col_map = _map_headers(header_cells)
    if not col_map:
        logger.warning("Could not map any column headers for %s", sale_date_str)
        return []

    records: list[dict] = []
    for tr in all_rows[1:]:
        tds = tr.find_all("td")
        if not tds:
            continue

        row: dict = {}
        for col_idx, field in col_map.items():
            if col_idx < len(tds):
                raw_text = tds[col_idx].get_text(separator=" ", strip=True)
                row[field] = re.sub(r"\s+", " ", raw_text).strip()
            else:
                row[field] = ""

        if not any(row.values()):
            continue
        if not row.get("clerk_file"):
            continue

        records.append(row)

    logger.info("Parsed %d rows from detail page for %s", len(records), sale_date_str)
    return records


def fetch_detail(context, sale_date: date) -> list[dict]:
    """Fetch and parse one sale date's detail page.

    The saledate parameter uses literal forward slashes (M/D/YYYY, no
    zero-padding).  The URL is pre-built as a string so Playwright's
    goto() does not percent-encode the slashes — the ASP server rejects
    percent-encoded slashes with a 403.

    Waits for TABLE_READY_SELECTOR before capturing HTML so that the
    JavaScript-rendered table is fully present in the DOM.  If the
    selector does not appear within TABLE_WAIT_TIMEOUT_MS it means the
    sale date has no listings; the function logs and returns [].
    """
    date_str = f"{sale_date.month}/{sale_date.day}/{sale_date.year}"
    url = f"{DETAIL_URL}?saledate={date_str}"
    logger.info("Fetching detail for %s", date_str)

    page = context.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        try:
            page.wait_for_selector(
                TABLE_READY_SELECTOR,
                timeout=TABLE_WAIT_TIMEOUT_MS,
            )
        except PlaywrightTimeoutError:
            logger.info(
                "Table selector not found for %s — sale date likely has no listings",
                date_str,
            )
            return []
        html = page.content()       
    finally:
        page.close()

    return parse_detail_page(html, date_str)


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

PROPERTY_EXISTS_SQL = text(
    """
    SELECT 1
    FROM   properties
    WHERE  county_fips = :fips
      AND  REGEXP_REPLACE(UPPER(parcel_id), '[^A-Z0-9]', '', 'g') = :norm_parcel
    LIMIT  1
    """
)

# Deduplication via WHERE NOT EXISTS — no unique constraint on mls_number.
# CAST(:raw_listing_json AS jsonb) — never ::jsonb syntax per project spec.
INSERT_LISTING_EVENT_SQL = text(
    """
    INSERT INTO listing_events (
        county_fips,
        parcel_id,
        mls_number,
        signal_tier,
        signal_type,
        source,
        list_price,
        list_date,
        workflow_status,
        notes,
        raw_listing_json,
        scraped_at,
        created_at,
        updated_at
    )
    SELECT
        :county_fips,
        :parcel_id,
        :mls_number,
        :signal_tier,
        :signal_type,
        :source,
        :list_price,
        :list_date,
        :workflow_status,
        :notes,
        CAST(:raw_listing_json AS jsonb),
        :scraped_at,
        :scraped_at,
        :scraped_at
    WHERE NOT EXISTS (
        SELECT 1
        FROM   listing_events le
        WHERE  le.mls_number = :mls_number
    )
    """
)

# ---------------------------------------------------------------------------
# Database upsert
# ---------------------------------------------------------------------------

def upsert_records(engine, rows: list[dict]) -> tuple[int, int, int]:
    """Resolve, filter, and batch-insert listing_events rows.

    Phase 1: single read-only connection checks property existence for all
    rows and builds the resolved parameter list.  No write locks held.

    Phase 2: each batch of BATCH_SIZE rows commits in its own engine.begin()
    transaction, matching the gis_ingest.py pattern.  A failure in batch N
    rolls back only batch N.

    Returns:
        (inserted, skipped_no_property, skipped_duplicate)
    """
    now = datetime.now(tz=timezone.utc)
    skipped_no_property = 0
    skipped_duplicate   = 0
    resolved: list[dict] = []

    with engine.connect() as conn:
        for row in rows:
            norm_parcel = _normalize_parcel(row.get("reference", ""))
            if not norm_parcel:
                logger.debug(
                    "Empty Reference for clerk_file=%s — skipping",
                    row.get("clerk_file"),
                )
                skipped_no_property += 1
                continue

            exists = conn.execute(
                PROPERTY_EXISTS_SQL,
                {"fips": COUNTY_FIPS, "norm_parcel": norm_parcel},
            ).fetchone()

            if exists is None:
                logger.debug(
                    "No property match: parcel=%s clerk_file=%s — skipping",
                    norm_parcel, row.get("clerk_file"),
                )
                skipped_no_property += 1
                continue

            status_val = (row.get("status") or "").strip()

            resolved.append(
                {
                    "county_fips":      COUNTY_FIPS,
                    "parcel_id":        norm_parcel[:30],
                    "mls_number":       row["clerk_file"][:50],
                    "signal_tier":      SIGNAL_TIER,
                    "signal_type":      SIGNAL_TYPE,
                    "source":           SOURCE,
                    "list_price":       _parse_opening_bid(
                                            row.get("opening_bid_amount", "")
                                        ),
                    "list_date":        _parse_sale_date(row["sales_date"])
                                        if row.get("sales_date") else None,
                    "workflow_status":  "new",
                    "notes":            f"Status: {status_val}" if status_val else None,
                    "raw_listing_json": json.dumps(row, default=str),
                    "scraped_at":       now,
                }
            )

    if not resolved:
        logger.info("No property-matched rows to insert.")
        return 0, skipped_no_property, 0

    total_inserted = 0
    for batch_num, batch in enumerate(_chunks(resolved, BATCH_SIZE), start=1):
        with engine.begin() as conn:
            result = conn.execute(INSERT_LISTING_EVENT_SQL, batch)
            inserted_this_batch = result.rowcount
        skipped_this_batch  = len(batch) - inserted_this_batch
        skipped_duplicate  += skipped_this_batch
        total_inserted     += inserted_this_batch
        logger.info(
            "Batch %d — inserted=%d  duplicates_skipped=%d  "
            "(running: inserted=%d no_property=%d duplicates=%d)",
            batch_num, inserted_this_batch, skipped_this_batch,
            total_inserted, skipped_no_property, skipped_duplicate,
        )

    return total_inserted, skipped_no_property, skipped_duplicate


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(
    mode: str,
    single_date: Optional[date] = None,
    engine=None,
) -> None:
    """Orchestrate the full scrape-and-ingest pipeline.

    A single BrowserContext is shared across all page fetches so that
    cookies established by the dates page carry through to detail pages.

    Args:
        mode:        'historical' | 'upcoming' | 'single'
        single_date: Required when mode == 'single'.
        engine:      SQLAlchemy engine; created from settings if None.
    """
    if engine is None:
        engine = create_engine(settings.sync_database_url)

    today = date.today()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        # One context = one cookie jar shared across all pages in this run.
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        try:
            # ------------------------------------------------------------------
            # Resolve target date list
            # ------------------------------------------------------------------
            if mode == "single":
                if single_date is None:
                    raise ValueError("single_date is required when mode='single'")
                target_dates = [single_date]
                logger.info("Mode=single  date=%s", single_date)

            else:
                all_dates = fetch_all_dates(context)
                _sleep()

                if mode == "historical":
                    cutoff = date(2019, 1, 1)
                    target_dates = [d for d in all_dates if d >= cutoff]
                    logger.info(
                        "Mode=historical  cutoff=%s  dates_selected=%d",
                        cutoff, len(target_dates),
                    )
                elif mode == "upcoming":
                    target_dates = [d for d in all_dates if d >= today]
                    logger.info(
                        "Mode=upcoming  dates_selected=%d", len(target_dates)
                    )
                else:
                    raise ValueError(f"Unknown mode: {mode!r}")

            if not target_dates:
                logger.info("No dates to process — exiting.")
                return

            # ------------------------------------------------------------------
            # Scrape each date
            # ------------------------------------------------------------------
            total_inserted         = 0
            total_skipped_property = 0
            total_skipped_dup      = 0

            for i, sale_date in enumerate(target_dates):
                try:
                    rows = fetch_detail(context, sale_date)
                except PlaywrightTimeoutError as exc:
                    logger.error("Timeout fetching %s: %s", sale_date, exc)
                    _sleep()
                    continue
                except Exception as exc:
                    logger.error(
                        "Unexpected error fetching %s: %s",
                        sale_date, exc, exc_info=True,
                    )
                    _sleep()
                    continue

                if rows:
                    try:
                        inserted, skipped_prop, skipped_dup = upsert_records(
                            engine, rows
                        )
                        total_inserted         += inserted
                        total_skipped_property += skipped_prop
                        total_skipped_dup      += skipped_dup
                        logger.info(
                            "Date %s — inserted=%d  skipped_no_property=%d  "
                            "skipped_duplicate=%d",
                            sale_date, inserted, skipped_prop, skipped_dup,
                        )
                    except Exception as exc:
                        logger.error(
                            "DB error processing date %s: %s",
                            sale_date, exc, exc_info=True,
                        )
                else:
                    logger.info(
                        "Date %s — 0 rows from detail page", sale_date
                    )

                if i < len(target_dates) - 1:
                    _sleep()

        finally:
            context.close()
            browser.close()

    logger.info(
        "Run complete — total_inserted=%d  skipped_no_property=%d  "
        "skipped_duplicate=%d",
        total_inserted, total_skipped_property, total_skipped_dup,
    )
