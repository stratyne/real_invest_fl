"""
real_invest_fl/ingest/cama/escambia.py
----------------------------------------
CAMA + sale history scraper for Escambia County, FL.

Data source: https://www.escpa.org/CAMA/Detail_a.aspx?s={parcel_id}

County-specific implementations:
    fetch_page()      — ECPA ASP.NET detail page, rate-limit aware
    parse_building()  — ECPA-specific HTML structure
    parse_sales()     — ECPA does not surface sale history on the CAMA
                        detail page. Returns empty list. Sale history
                        for Escambia requires a separate source.

ECPA rate limiting:
    Server enforces ~100 requests per ~3-minute window.
    Soft-block signature: 302 redirect to escpa.org root, or response
    body missing "Parcel ID:" marker.

Usage:
    python -m real_invest_fl.ingest.cama.escambia [options]

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
from pathlib import Path
from typing import Optional

import httpx
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from real_invest_fl.ingest.cama import base  # noqa: E402

logger = logging.getLogger("cama.escambia")

# ── county identity ───────────────────────────────────────────────────────────
COUNTY_FIPS = "12033"
SOURCE_NAME = "escpa_cama"

# ── HTTP ──────────────────────────────────────────────────────────────────────
CAMA_URL = "https://www.escpa.org/CAMA/Detail_a.aspx?s={parcel_id}"

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
    "Referer": "https://www.escpa.org/CAMA/Search.aspx",
}

# Text that must appear in a valid ECPA CAMA response
VALID_PAGE_MARKER = "Parcel ID:"


# ── fetch ─────────────────────────────────────────────────────────────────────

async def fetch_page(
    client: httpx.AsyncClient,
    parcel_id: str,
) -> Optional[str]:
    """
    Fetch the ECPA CAMA detail page for a single parcel.

    Soft-block detection:
        ECPA rate-limits by redirecting to the homepage when the
        per-window quota (~100 requests per ~3 minutes) is exceeded.
        Detected by redirect history pointing to escpa.org root, or
        by absence of "Parcel ID:" in the response body.

    Returns:
        HTML string on success.
        base.SOFT_BLOCK sentinel on soft-block — caller stops the run.
        None on transient failure (timeout, HTTP error, retries exhausted).
    """
    url = CAMA_URL.format(parcel_id=parcel_id)

    for attempt in range(3):
        try:
            resp = await client.get(url, timeout=15.0)

            # Soft-block: redirect history points to escpa.org root
            soft_blocked = False
            if resp.history:
                for h in resp.history:
                    loc = h.headers.get("location", "").rstrip("/").lower()
                    if loc in (
                        "https://www.escpa.org",
                        "https://escpa.org",
                    ):
                        soft_blocked = True
                        break

            # Soft-block: final response missing parcel marker
            if not soft_blocked and resp.status_code == 200:
                if VALID_PAGE_MARKER not in resp.text:
                    soft_blocked = True

            if soft_blocked:
                logger.error(
                    "Parcel %s — ECPA soft block detected. "
                    "Rate limit tripped. Wait ~3 minutes.",
                    parcel_id,
                )
                return base.SOFT_BLOCK

            if resp.status_code == 200:
                if "General Information" not in resp.text:
                    logger.warning(
                        "Parcel %s — unexpected page content on attempt %d",
                        parcel_id, attempt + 1,
                    )
                    await asyncio.sleep(3.0)
                    continue
                return resp.text

            if resp.status_code == 404:
                logger.warning("Parcel %s — not found (404)", parcel_id)
                return None

            logger.warning(
                "Parcel %s — HTTP %s on attempt %d",
                parcel_id, resp.status_code, attempt + 1,
            )
            await asyncio.sleep(3.0)

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

def parse_building(html: str, parcel_id: str) -> dict:
    """
    Parse building characteristics from the ECPA CAMA detail page.

    ECPA page structure:
        - Building data in <table id="ctl00_MasterPlaceHolder_tblBldgs">
        - Year Built in <th> header: "Year Built: YYYY"
        - Total SF in <th> or <span style="background-color:LightGrey">:
          "NNNN Total SF"
        - Structural fields as <b>LABEL</b><i>VALUE</i> pairs
        - Zoning in <div id="ctl00_MasterPlaceHolder_MapBodyStats">

    Returns dict with canonical keys matching base.coerce_building()
    input expectations.
    """
    soup = BeautifulSoup(html, "html.parser")
    fields: dict[str, str] = {}

    # ── Zoning ────────────────────────────────────────────────────────── #
    map_stats = soup.find(id="ctl00_MasterPlaceHolder_MapBodyStats")
    if map_stats:
        text_content = map_stats.get_text(separator="\n")
        for line in text_content.splitlines():
            line = line.strip()
            if (
                line
                and line not in (
                    "Zoned:", "Approx. Acreage:", "Section Map Id:"
                )
                and not line.startswith("CA")
                and not re.match(r"^\d+\.\d+$", line)
                and re.match(r"^[A-Z0-9\-]{2,10}$", line)
            ):
                fields["zoning"] = line
                break

    # ── Building table ────────────────────────────────────────────────── #
    building_tables = soup.find(id="ctl00_MasterPlaceHolder_tblBldgs")
    if not building_tables:
        logger.warning("Parcel %s — no building table found", parcel_id)
        return fields

    inner_tables = building_tables.find_all("table", recursive=True)

    for tbl in inner_tables:
        th = tbl.find("th")
        if not th:
            continue
        th_text = th.get_text(separator=" ", strip=True)

        # Year Built
        yr_match = re.search(
            r"Year Built:\s*(\d{4})", th_text, re.IGNORECASE
        )
        if yr_match and "act_yr_blt" not in fields:
            fields["act_yr_blt"] = yr_match.group(1)

        # Total SF from <th>
        sf_match = re.search(r"(\d+)\s+Total SF", th_text, re.IGNORECASE)
        if sf_match and "living_area" not in fields:
            fields["living_area"] = sf_match.group(1)

        # Structural fields as <b>LABEL</b><i>VALUE</i>
        for b_tag in tbl.find_all("b"):
            label_raw = b_tag.get_text(strip=True).upper()
            i_tag = b_tag.find_next_sibling("i")
            if not i_tag:
                continue
            value_raw = i_tag.get_text(strip=True)
            if not value_raw:
                continue

            if label_raw == "FOUNDATION" and "foundation" not in fields:
                fields["foundation"] = value_raw

            elif label_raw == "EXTERIOR WALL":
                if "exterior_wall" in fields:
                    fields["exterior_wall"] = (
                        fields["exterior_wall"] + " / " + value_raw
                    )
                else:
                    fields["exterior_wall"] = value_raw

            elif label_raw == "ROOF COVER" and "roof_type" not in fields:
                fields["roof_type"] = value_raw

            elif label_raw in ("BEDROOMS", "NO. BEDROOMS") \
                    and "bedrooms" not in fields:
                fields["bedrooms"] = value_raw

            elif label_raw in (
                "BATHROOMS", "NO. BATHROOMS", "FULL BATHS"
            ) and "bathrooms" not in fields:
                fields["bathrooms"] = value_raw

            elif label_raw in ("QUALITY", "GRADE") \
                    and "quality_code" not in fields:
                fields["quality_code"] = value_raw

            elif label_raw == "CONDITION" \
                    and "condition_code" not in fields:
                fields["condition_code"] = value_raw

    # Total SF from LightGrey span (fallback)
    if "living_area" not in fields and building_tables:
        for span in building_tables.find_all("span"):
            style = span.get("style", "")
            if "LightGrey" in style or "lightgrey" in style.lower():
                span_text = span.get_text(strip=True)
                sf_match = re.search(
                    r"(\d+)\s+Total SF", span_text, re.IGNORECASE
                )
                if sf_match:
                    fields["living_area"] = sf_match.group(1)
                    break

    if not fields:
        logger.warning(
            "Parcel %s — no CAMA fields parsed from ECPA page", parcel_id
        )

    return fields


def parse_sales(html: str, parcel_id: str) -> list[dict]:
    """
    ECPA CAMA detail page does not surface sale history.

    Sale history for Escambia County is available from the Escambia
    Clerk of Court (escambiaclerk.com) and is captured separately
    via escambia_taxdeed_clerk.py and the lis pendens / foreclosure
    staging parsers.

    Returns empty list always.
    """
    return []


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
        default_delay=1.5,        # ECPA tested minimum
        default_delay_max=4.0,    # ECPA tested maximum
        rest_every=100,           # ECPA rate limit window
        rest_seconds=270.0,       # ECPA rest duration
    )
