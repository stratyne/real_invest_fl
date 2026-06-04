"""
real_invest_fl/ingest/cama/santa_rosa.py
------------------------------------------
CAMA + sale history scraper for Santa Rosa County, FL.

Data source:
    https://parcelcard.srcpa.gov/?parcel={parcel_id}&baseUrl=http://srcpa.gov/

The parcelcard endpoint is fully server-rendered. No JavaScript
execution, session management, auth, or cookies required.
A plain httpx GET is sufficient.

The parcelcard page is a React/Remix application rendered server-side.
HTML structure uses Tailwind CSS classes. Building fields are in a
two-column <td> grid where bold <td> cells contain abbreviated labels
and adjacent <td> cells contain values. There are no data-cell
attributes or named container divs.

County-specific implementations:
    fetch_page()      - plain GET with soft-block detection
    parse_building()  - two-column <td> label/value grid pattern
    parse_sales()     - Sales section table, interleaved grantor/grantee rows

Soft-block detection:
    Valid pages contain window.__remixContext with full parcel data.
    remixContext absent entirely → soft block, stop run.
    remixContext present but empty:true → parcel not in SRCPA system,
    skip cleanly and continue. Do not stop on not-found parcels.

Previous data source (parcelview.srcpa.gov) was replaced by
parcelcard.srcpa.gov. SOURCE_NAME updated to srcpa_parcelcard.
data_source_status rows with source = srcpa_parcelview are superseded.

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
import re
import sys
import json
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
SOURCE_NAME = "srcpa_parcelcard"

# ── HTTP ──────────────────────────────────────────────────────────────────────
PARCELCARD_URL = (
    "https://parcelcard.srcpa.gov/"
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


# Mapping: card abbreviation → canonical key for coerce_building()
# All abbreviations confirmed from live parcelcard HTML 2026-05-24.
_ABBREV_MAP: dict[str, str] = {
    "extw": "exterior_wall",
    "RCVR": "roof_type",
    "fndn": "foundation",
    "Bath": "bathrooms",
    "BED":  "bedrooms",
    "qual": "quality_code",
}

# AYB and EYB are sourced from remixContext JSON, not the field grid.
# See _parse_ayb_eyb_from_context().


# ── fetch ─────────────────────────────────────────────────────────────────────

async def fetch_page(
    client: httpx.AsyncClient,
    parcel_id: str,
) -> Optional[str]:
    """
    Fetch the parcelcard page for a single Santa Rosa parcel.

    Soft-block detection:
        remixContext absent entirely → soft block, stop run.
        remixContext present but empty:true → parcel not in SRCPA system,
        skip cleanly and continue run. Do not stop on not-found parcels.

    Returns:
        HTML string on success.
        base.SOFT_BLOCK sentinel when remixContext is absent.
        None when parcel not found in SRCPA system, or on transient
        failure (timeout, HTTP error, retries exhausted).
    """
    url = PARCELCARD_URL.format(parcel_id=parcel_id)

    for attempt in range(3):
        try:
            resp = await client.get(url, timeout=20.0)

            if resp.status_code == 404:
                logger.warning("Parcel %s - 404 not found", parcel_id)
                return None

            if resp.status_code != 200:
                logger.warning(
                    "Parcel %s - HTTP %s on attempt %d",
                    parcel_id, resp.status_code, attempt + 1,
                )
                await asyncio.sleep(3.0)
                continue

            # Soft block: remixContext absent - unexpected server response
            if "window.__remixContext" not in resp.text:
                logger.error(
                    "Parcel %s - soft block or unexpected response "
                    "(remixContext absent). Stopping run.",
                    parcel_id,
                )
                return base.SOFT_BLOCK

            # Parcel not found in SRCPA system - skip cleanly, do not stop run
            if '"empty":true' in resp.text or '"empty": true' in resp.text:
                logger.warning(
                    "Parcel %s - not found in SRCPA system (empty:true). Skipping.",
                    parcel_id,
                )
                return None

            return resp.text

        except httpx.TimeoutException:
            logger.warning(
                "Parcel %s - timeout on attempt %d", parcel_id, attempt + 1
            )
            await asyncio.sleep(3.0)
        except httpx.RequestError as exc:
            logger.warning(
                "Parcel %s - request error: %s", parcel_id, exc
            )
            break

    logger.error("Parcel %s - all attempts failed", parcel_id)
    return None


# ── parsers ───────────────────────────────────────────────────────────────────

def _strip_code(val: str) -> str:
    """
    Strip trailing parenthetical code from parcelcard field values.
    e.g. 'BRICK (20)'              → 'BRICK'
         'BRICK(20)'               → 'BRICK'
         'CLASS 4(04'              → 'CLASS 4'  (malformed, no closing paren)
         'TIMBERLINE SHINGLE (06)' → 'TIMBERLINE SHINGLE'
    """
    return re.sub(r"\s*\([^)]*\)?$", "", val).strip()

def _parse_field_grid(soup: BeautifulSoup) -> dict[str, str]:
    """
    Extract building fields from the two-column <td> label/value grid.

    The parcelcard HTML uses a repeating pattern within <tbody> rows:
        <tr>
            <td class="font-bold">LABEL</td>
            <td>VALUE</td>
            <td class="font-bold">LABEL</td>  ← optional second pair
            <td>VALUE</td>
        </tr>

    Bold <td> cells contain abbreviated field labels. The immediately
    following sibling <td> contains the value. Percentage rows (e.g.
    "40%", "70%") appear as non-bold <td> cells and are skipped.

    Returns dict of {abbreviation: value_text} for all non-empty pairs.
    # Searches entire document - scoped to known abbreviations via _ABBREV_MAP
    # in the caller. AYB/EYB intentionally excluded from _ABBREV_MAP since
    # they are sourced from remixContext JSON in _parse_ayb_eyb_from_context().
    """
    fields: dict[str, str] = {}

    for td in soup.find_all("td", class_=lambda c: c and "font-bold" in c):
        label = td.get_text(strip=True)
        if not label:
            continue
        # Value is the next sibling <td>
        next_td = td.find_next_sibling("td")
        if next_td is None:
            continue
        value = next_td.get_text(strip=True)
        if value:
            fields[label] = value

    return fields


def _parse_remix_context(html: str) -> dict:
    """
    Extract parcel data from the window.__remixContext JSON embedded in
    the parcelcard server-rendered HTML.

    Uses string split rather than regex to handle large JSON payloads
    safely. The remixContext JSON is terminated by ';</script>' which
    is a reliable boundary on this page.

    Returns the routes/_index loader data dict, or empty dict if not found.
    """
    marker = "window.__remixContext = "
    start = html.find(marker)
    if start == -1:
        return {}
    start += len(marker)
    end = html.find(";</script>", start)
    if end == -1:
        return {}
    try:
        ctx = json.loads(html[start:end])
        return (
            ctx
            .get("state", {})
            .get("loaderData", {})
            .get("routes/_index", {})
        )
    except (json.JSONDecodeError, AttributeError):
        return {}


def _parse_heated_area(loader_data: dict) -> Optional[str]:
    """
    Extract heated square footage from the remixContext loader data.

    Path: buildings.units[0].squareFeet.heated
    Returns string representation of heated area, or None if absent or zero.
    """
    try:
        heated = (
            loader_data
            .get("buildings", {})
            .get("units", [{}])[0]
            .get("squareFeet", {})
            .get("heated")
        )
        if heated and int(heated) > 0:
            return str(int(heated))
    except (IndexError, TypeError, ValueError):
        pass
    return None


def _parse_ayb_eyb_from_context(loader_data: dict) -> tuple[Optional[str], Optional[str]]:
    """
    Extract Actual Year Built and Effective Year Built from remixContext.

    Path: buildings.units[0].yearBuilt.{actual,effective}
    Returns (ayb, eyb) as strings, either may be None.
    """
    try:
        year_built = (
            loader_data
            .get("buildings", {})
            .get("units", [{}])[0]
            .get("yearBuilt", {})
        )
        ayb = year_built.get("actual")
        eyb = year_built.get("effective")
        return (
            str(int(ayb)) if ayb else None,
            str(int(eyb)) if eyb else None,
        )
    except (IndexError, TypeError, ValueError):
        return None, None


def _parse_zoning_from_context(loader_data: dict) -> Optional[str]:
    """
    Extract zoning code from remixContext.

    Path: zonings[0].code
    The parcelcard HTML has no zoning field - it is only in the JSON.
    Returns zoning code string, or None if absent.
    """
    try:
        zonings = loader_data.get("zonings", [])
        if zonings:
            code = zonings[0].get("code", "").strip()
            return code if code else None
    except (IndexError, TypeError):
        pass
    return None


def parse_building(html: str, parcel_id: str) -> dict:
    """
    Parse building characteristics from the Santa Rosa parcelcard page.

    Parcelcard HTML structure (confirmed 2026-05-24):
        - Building fields in two-column <td> bold-label/value grid
        - Abbreviated labels: extw, RCVR, fndn, Bath, BED, qual
        - Heated area, AYB, EYB, and zoning sourced from
          window.__remixContext JSON (HTML summary table unreliable)
        - remixContext is present in server-rendered HTML - no JS required

    Returns dict with canonical keys matching base.coerce_building()
    input expectations. Returns empty dict if no building fields found.
    """
    soup = BeautifulSoup(html, "html.parser")
    fields: dict[str, str] = {}

    # ── remixContext JSON ─────────────────────────────────────────────── #
    loader_data = _parse_remix_context(html)

    # ── Field grid (extw, RCVR, fndn, Bath, BED, qual) ───────────────── #
    raw_grid = _parse_field_grid(soup)

    for abbrev, canonical in _ABBREV_MAP.items():
        val = raw_grid.get(abbrev, "")
        if val:
            fields[canonical] = _strip_code(val)

    # ── Heated area - from remixContext, not HTML table ───────────────── #
    heated = _parse_heated_area(loader_data)
    if heated:
        fields["living_area"] = heated

    # ── AYB / EYB - from remixContext ─────────────────────────────────── #
    ayb, eyb = _parse_ayb_eyb_from_context(loader_data)
    if ayb:
        fields["act_yr_blt"] = ayb
    if eyb:
        fields["eff_yr_blt"] = eyb

    # ── Zoning - from remixContext (not in HTML card) ─────────────────── #
    zoning = _parse_zoning_from_context(loader_data)
    if zoning:
        fields["zoning"] = zoning

    if not fields:
        logger.warning(
            "Parcel %s - no building fields parsed from parcelcard", parcel_id
        )

    return fields


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    base.main(
        county_fips=COUNTY_FIPS,
        source_name=SOURCE_NAME,
        fetch_page_fn=fetch_page,
        parse_building_fn=parse_building,
        headers=HEADERS,
        target_dor_ucs=["001"],
        default_delay=1.0,
        default_delay_max=3.0,
        rest_every=500,
        rest_seconds=300.0,
    )
