"""
real_invest_fl/ingest/cama/santa_rosa.py
------------------------------------------
CAMA + sale history scraper for Santa Rosa County, FL.

Data source:
    https://parcelview.srcpa.gov/?parcel={parcel_id}&baseUrl=http://srcpa.gov/

The parcelview endpoint is fully server-rendered. No JavaScript
execution, session management, auth, or cookies required.
A plain httpx GET is sufficient.

County-specific implementations:
    fetch_page()      — plain GET with soft-block detection
    parse_building()  — data-cell attribute pattern
    parse_sales()     — data-cell attribute pattern, all transactions

Soft-block detection:
    Valid pages contain "residentialBuildingsContainer".
    Absence of this string indicates a disclaimer-only response.

Usage:
    python -m real_invest_fl.ingest.cama.santa_rosa [options]

See base.py for all available options.

ETHICAL / LEGAL NOTICE:
    Public government website. All data is public record under Florida
    Statute 119. Minimum delay 1.0s enforced by base.main().
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

import httpx
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from real_invest_fl.ingest.cama import base  # noqa: E402

logger = logging.getLogger("cama.santa_rosa")

# ── county identity ───────────────────────────────────────────────────────────
COUNTY_FIPS = "12113"
SOURCE_NAME = "srcpa_parcelview"

# ── HTTP ──────────────────────────────────────────────────────────────────────
PARCELVIEW_URL = (
    "https://parcelview.srcpa.gov/"
    "?parcel={parcel_id}&baseUrl=http://srcpa.gov/"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://srcpa.gov/",
}

# Text that must appear in a valid parcelview response
VALID_PAGE_MARKER = "residentialBuildingsContainer"


# ── fetch ─────────────────────────────────────────────────────────────────────

async def fetch_page(
    client: httpx.AsyncClient,
    parcel_id: str,
) -> Optional[str]:
    """
    Fetch the parcelview page for a single Santa Rosa parcel.

    Soft-block detection:
        Valid pages contain "residentialBuildingsContainer".
        Pages that only contain the disclaimer text do not.

    Returns:
        HTML string on success.
        base.SOFT_BLOCK sentinel on soft-block.
        None on transient failure.
    """
    url = PARCELVIEW_URL.format(parcel_id=parcel_id)

    for attempt in range(3):
        try:
            resp = await client.get(url, timeout=20.0)

            if resp.status_code == 404:
                logger.warning("Parcel %s — 404 not found", parcel_id)
                return None

            if resp.status_code != 200:
                logger.warning(
                    "Parcel %s — HTTP %s on attempt %d",
                    parcel_id, resp.status_code, attempt + 1,
                )
                await asyncio.sleep(3.0)
                continue

            if VALID_PAGE_MARKER not in resp.text:
                logger.error(
                    "Parcel %s — soft block detected "
                    "(no parcel data in response). Stopping run.",
                    parcel_id,
                )
                return base.SOFT_BLOCK

            return resp.text

        except httpx.TimeoutException:
            logger.warning(
                "Parcel %s — timeout on attempt %d", parcel_id, attempt + 1
            )
            await asyncio.sleep(3.0)
        except httpx.RequestError as exc:
            logger.warning(
                "Parcel %s — request error: %s", parcel_id, exc
            )
            break

    logger.error("Parcel %s — all attempts failed", parcel_id)
    return None


# ── parsers ───────────────────────────────────────────────────────────────────

def _cell(container, label: str) -> str:
    """
    Extract text from the first <td data-cell="{label}"> within container.

    This is the universal parse pattern for parcelview — every data
    value on the page uses this structure. The data-cell attribute value
    exactly matches the visible column header text.

    Returns empty string if the cell is not found.
    """
    td = container.find("td", attrs={"data-cell": label})
    if td is None:
        return ""
    return td.get_text(strip=True)


def parse_building(html: str, parcel_id: str) -> dict:
    """
    Parse building characteristics from the Santa Rosa parcelview page.

    Targets the first building table within residentialBuildingsContainer.
    Each field is a <tr> with <th> label and <td data-cell="LABEL"> value.
    Uses _cell() for all extractions — no regex, no sibling traversal.

    Zoning is in a separate zoningContainer div using the same pattern.

    Returns dict with canonical keys matching base.coerce_building()
    input expectations. Returns empty dict if no building table found.
    """
    soup = BeautifulSoup(html, "html.parser")
    fields: dict[str, str] = {}

    container = soup.find(id="residentialBuildingsContainer")
    if not container:
        logger.warning(
            "Parcel %s — no buildings container found", parcel_id
        )
        return fields

    # First building table — identified by <caption> containing "Building"
    building_table = None
    for tbl in container.find_all("table"):
        caption = tbl.find("caption")
        if caption and "Building" in caption.get_text():
            building_table = tbl
            break

    if not building_table:
        logger.warning(
            "Parcel %s — no building table found in container", parcel_id
        )
        return fields

    # Field map: parcelview label → canonical key for coerce_building()
    field_map = {
        "Exterior Walls":      "exterior_wall",
        "Roof Cover":          "roof_type",
        "Foundation":          "foundation",
        "Heated Area":         "living_area",
        "Bathrooms":           "bathrooms",
        "Bedrooms":            "bedrooms",
        "Actual Year Built":   "act_yr_blt",
        "Effective Year Built": "eff_yr_blt",
    }

    for label, canonical in field_map.items():
        val = _cell(building_table, label)
        if val:
            fields[canonical] = val

    # Zoning
    zoning_container = soup.find(id="zoningContainer")
    if zoning_container:
        code = _cell(zoning_container, "Code")
        if code:
            fields["zoning"] = code

    if not fields:
        logger.warning(
            "Parcel %s — no building fields parsed", parcel_id
        )

    return fields


def parse_sales(html: str, parcel_id: str) -> list[dict]:
    """
    Parse all sale transactions from the Santa Rosa parcelview page.

    Targets salesContainer div. Each data <tr> contains <td data-cell>
    cells for all transaction fields. Header rows (containing only <th>)
    are skipped automatically — they yield no data-cell td matches.

    Returns list of raw dicts, one per sale. Returns empty list if
    no sales section found or no rows present.
    """
    soup = BeautifulSoup(html, "html.parser")
    sales: list[dict] = []

    container = soup.find(id="salesContainer")
    if not container:
        logger.warning(
            "Parcel %s — no sales container found", parcel_id
        )
        return sales

    for row in container.find_all("tr"):
        # Skip header rows — no data-cell td present
        if not row.find("td", attrs={"data-cell": True}):
            continue

        sale = {
            "multi_parcel":       _cell(row, "Multi-Parcel"),
            "sale_date":          _cell(row, "Sale Date"),
            "sale_price":         _cell(row, "Sale Price"),
            "instrument_type":    _cell(row, "Instrument"),
            "qualification_code": _cell(row, "Qualification"),
            "sale_type":          _cell(row, "Sale Type"),
            "grantor":            _cell(row, "Grantor"),
            "grantee":            _cell(row, "Grantee"),
        }

        # Only include rows that have at least a sale date
        if sale["sale_date"]:
            sales.append(sale)

    return sales


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    base.main(
        county_fips=COUNTY_FIPS,
        source_name=SOURCE_NAME,
        fetch_page_fn=fetch_page,
        parse_building_fn=parse_building,
        parse_sales_fn=parse_sales,
        headers=HEADERS,
        target_dor_ucs=["001"],   # Single-family residential
        default_delay=1.0,        # No robots.txt, modern nginx server
        default_delay_max=3.0,    # No documented rate limit
        rest_every=500,          # No rest pauses — no rate limit evidence
        rest_seconds=300.0,
    )
