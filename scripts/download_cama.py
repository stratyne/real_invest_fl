"""
scripts/download_cama.py
------------------------
Per-parcel CAMA scraper for Escambia County, FL.

Reads all MQI-qualified parcels from the properties table, fetches
https://escpa.org/CAMA/Detail_a.aspx?s={parcel_id} for each one,
parses the building characteristic fields, and writes results back
to the properties table.

Writes to:
    raw_cama_json       — full parsed field dict as JSONB
    foundation_type     — VARCHAR(100)
    exterior_wall       — VARCHAR(100)
    roof_type           — VARCHAR(100)
    cama_quality_code   — VARCHAR(10)
    cama_condition_code — VARCHAR(10)
    bedrooms            — INTEGER
    bathrooms           — NUMERIC
    tot_lvg_area        — INTEGER  (CAMA living area overrides NAL if present)
    act_yr_blt          — INTEGER  (CAMA year built overrides NAL if present)
    zoning              — VARCHAR(20)
    cama_enriched_at    — TIMESTAMPTZ

Usage:
    python scripts/download_cama.py [--limit N] [--parcel PARCEL_ID]
    [--dry-run] [--delay 2.0] [--force]

Options:
    --limit N           Process only N parcels (default: all qualified)
    --parcel PARCEL_ID  Process a single parcel by ID (for testing)
    --dry-run           Fetch and parse but do not write to DB
    --delay SECONDS     Delay between requests in seconds (default: 2.0)
    --force             Re-fetch parcels that already have cama_enriched_at set

ETHICAL / LEGAL NOTICE:
    This scraper targets a public government website (Escambia County
    Property Appraiser). Requests are rate-limited by default to one
    every 2 seconds. Do not reduce the delay below 1.0 second.
    All data retrieved is public record under Florida Statute 119.
"""

from __future__ import annotations

import json
import argparse
import asyncio
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# ── path bootstrap ────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import settings  # noqa: E402

# ── logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("download_cama")

# ── constants ─────────────────────────────────────────────────────────────────
CAMA_URL = "https://escpa.org/CAMA/Detail_a.aspx?s={parcel_id}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# Maps raw ECPA label text → canonical field name
# Labels are taken directly from the ECPA CAMA detail page HTML.
# If ECPA changes their labels, update this map — do not change the
# canonical field names.
LABEL_MAP: dict[str, str] = {
    # Year / area
    "year built":               "year_built",
    "actual year built":        "year_built",
    "effective year built":     "eff_year_built",
    "living area":              "living_area",
    "total living area":        "living_area",
    "heated area":              "living_area",

    # Structural
    "foundation":               "foundation",
    "foundation type":          "foundation",
    "exterior wall":            "exterior_wall",
    "exterior":                 "exterior_wall",
    "roof cover":               "roof_type",
    "roof type":                "roof_type",
    "roof":                     "roof_type",

    # Rooms
    "bedrooms":                 "bedrooms",
    "beds":                     "bedrooms",
    "bathrooms":                "bathrooms",
    "baths":                    "bathrooms",
    "full baths":               "bathrooms",

    # Quality / condition
    "quality":                  "quality_code",
    "grade":                    "quality_code",
    "condition":                "condition_code",

    # Zoning
    "zoning":                   "zoning",
    "zoning code":              "zoning",
}


# ── HTML parser ───────────────────────────────────────────────────────────────

def parse_cama_html(html: str, parcel_id: str) -> dict:
    """
    Parse the ECPA CAMA detail page HTML into a flat field dict.

    The ECPA page uses a specific structure for building data:
    - Building header <th> contains: Year Built, Effective Year, Total SF
    - Structural elements are in <span> as <b>FIELD</b>-<i>VALUE</i> pairs
    - Zoning is in the Parcel Information <td> as plain text after a <br/>
    - Bedrooms and bathrooms are NOT labeled — not available on this page

    Returns a dict with canonical field names as keys and raw string
    values. Returns an empty dict if the page contains no parseable data.
    """
    soup = BeautifulSoup(html, "html.parser")
    fields: dict[str, str] = {}

    # ------------------------------------------------------------------ #
    # Step 1 — Extract zoning from Parcel Information section             #
    # Zoning appears as "R-1AA" after a <br/> following the word "Zoned:" #
    # ------------------------------------------------------------------ #
    map_stats = soup.find(id="ctl00_MasterPlaceHolder_MapBodyStats")
    if map_stats:
        text_content = map_stats.get_text(separator="\n")
        for line in text_content.splitlines():
            line = line.strip()
            # Zoning value is a short alphanumeric code on its own line
            # after "Zoned:" — filter out empty lines and known non-values
            if line and line not in ("Zoned:", "Approx. Acreage:", "Section Map Id:") \
                    and not line.startswith("CA") \
                    and not re.match(r"^\d+\.\d+$", line) \
                    and re.match(r"^[A-Z0-9\-]{2,10}$", line):
                fields["zoning"] = line
                break

    # ------------------------------------------------------------------ #
    # Step 2 — Process each building block                                #
    # There may be multiple buildings; we use the first/primary one.      #
    # ------------------------------------------------------------------ #
    building_tables = soup.find(id="ctl00_MasterPlaceHolder_tblBldgs")
    if not building_tables:
        logger.warning("Parcel %s — no building table found", parcel_id)
        return fields

    # Each building is wrapped in an inner <table> with a <th> header
    inner_tables = building_tables.find_all("table", recursive=True)

    for tbl in inner_tables:
        th = tbl.find("th")
        if not th:
            continue
        th_text = th.get_text(separator=" ", strip=True)

        # ── Year Built ──────────────────────────────────────────────── #
        yr_match = re.search(r"Year Built:\s*(\d{4})", th_text, re.IGNORECASE)
        if yr_match and "year_built" not in fields:
            fields["year_built"] = yr_match.group(1)

        # ── Total SF ────────────────────────────────────────────────── #
        # In a separate nested <th>: "Areas - 1270 Total SF"
        sf_match = re.search(r"(\d+)\s+Total SF", th_text, re.IGNORECASE)
        if sf_match and "living_area" not in fields:
            fields["living_area"] = sf_match.group(1)

        # ── Structural Elements span ─────────────────────────────────  #
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
                    fields["exterior_wall"] = fields["exterior_wall"] + " / " + value_raw
                else:
                    fields["exterior_wall"] = value_raw

            elif label_raw == "ROOF COVER" and "roof_type" not in fields:
                fields["roof_type"] = value_raw

            elif label_raw in ("BEDROOMS", "NO. BEDROOMS") and "bedrooms" not in fields:
                fields["bedrooms"] = value_raw

            elif label_raw in ("BATHROOMS", "NO. BATHROOMS", "FULL BATHS") \
                    and "bathrooms" not in fields:
                fields["bathrooms"] = value_raw

            elif label_raw in ("QUALITY", "GRADE") and "quality_code" not in fields:
                fields["quality_code"] = value_raw

            elif label_raw == "CONDITION" and "condition_code" not in fields:
                fields["condition_code"] = value_raw

    # ------------------------------------------------------------------ #
    # Step 3 — Extract Total SF from the LightGrey span in tblBldgs      #
    # The Areas line is in a <span> with background-color:LightGrey,     #
    # not in a <th>. Must be searched separately after the table loop.   #
    # ------------------------------------------------------------------ #
    if "living_area" not in fields and building_tables:
        for span in building_tables.find_all("span"):
            style = span.get("style", "")
            if "LightGrey" in style or "lightgrey" in style.lower():
                span_text = span.get_text(strip=True)
                sf_match = re.search(r"(\d+)\s+Total SF", span_text, re.IGNORECASE)
                if sf_match:
                    fields["living_area"] = sf_match.group(1)
                    break
                    
    # Stop after we have both year_built and living_area from the
    # primary building — do not accumulate data from outbuildings
    # Note: we do NOT break early — we let the loop complete all
    # inner tables so the Areas <th> is always reached.

    if not fields:
        logger.warning(
            "Parcel %s — no CAMA fields parsed — page layout may have changed",
            parcel_id,
        )

    return fields


def coerce_cama_fields(raw: dict, parcel_id: str) -> dict:
    """
    Coerce raw string values from parse_cama_html into typed Python
    values ready for the properties table columns.

    Returns a dict of column_name → typed value.
    All values may be None if the field was absent or unparseable.
    """
    def _clean_int(val: str | None) -> Optional[int]:
        if not val:
            return None
        digits = re.sub(r"[^\d]", "", val)
        return int(digits) if digits else None

    def _clean_decimal(val: str | None) -> Optional[float]:
        if not val:
            return None
        cleaned = re.sub(r"[^\d.]", "", val)
        try:
            return float(cleaned)
        except ValueError:
            return None

    def _clean_str(val: str | None, max_len: int) -> Optional[str]:
        if not val:
            return None
        s = val.strip()
        return s[:max_len] if s else None

    year_built   = _clean_int(raw.get("year_built"))
    living_area  = _clean_int(raw.get("living_area"))
    bedrooms     = _clean_int(raw.get("bedrooms"))
    bathrooms    = _clean_decimal(raw.get("bathrooms"))
    foundation   = _clean_str(raw.get("foundation"), 100)
    ext_wall     = _clean_str(raw.get("exterior_wall"), 100)
    roof         = _clean_str(raw.get("roof_type"), 100)
    quality      = _clean_str(raw.get("quality_code"), 10)
    condition    = _clean_str(raw.get("condition_code"), 10)
    zoning       = _clean_str(raw.get("zoning"), 20)

    # Sanity checks — log but do not discard
    if year_built and not (1800 <= year_built <= datetime.now().year):
        logger.warning("Parcel %s — suspicious year_built value: %s", parcel_id, year_built)
        year_built = None

    if bedrooms and not (0 <= bedrooms <= 20):
        logger.warning("Parcel %s — suspicious bedrooms value: %s", parcel_id, bedrooms)
        bedrooms = None

    if bathrooms and not (0.0 <= bathrooms <= 20.0):
        logger.warning("Parcel %s — suspicious bathrooms value: %s", parcel_id, bathrooms)
        bathrooms = None

    return {
        "act_yr_blt":          year_built,
        "tot_lvg_area":        living_area,
        "bedrooms":            bedrooms,
        "bathrooms":           bathrooms,
        "foundation_type":     foundation,
        "exterior_wall":       ext_wall,
        "roof_type":           roof,
        "cama_quality_code":   quality,
        "cama_condition_code": condition,
        "zoning":              zoning,
    }


# ── database helpers ──────────────────────────────────────────────────────────

async def fetch_qualified_parcel_ids(
    session: AsyncSession,
    limit: Optional[int],
    force: bool,
) -> list[str]:
    """
    Return parcel_id values for all MQI-qualified properties.
    If force=False, skip parcels that already have cama_enriched_at set.
    """
    if force:
        sql = text("""
            SELECT parcel_id
            FROM properties
            WHERE mqi_qualified = true
            ORDER BY parcel_id
            LIMIT :lim
        """) if limit else text("""
            SELECT parcel_id
            FROM properties
            WHERE mqi_qualified = true
            ORDER BY parcel_id
        """)
    else:
        sql = text("""
            SELECT parcel_id
            FROM properties
            WHERE mqi_qualified = true
              AND cama_enriched_at IS NULL
            ORDER BY parcel_id
            LIMIT :lim
        """) if limit else text("""
            SELECT parcel_id
            FROM properties
            WHERE mqi_qualified = true
              AND cama_enriched_at IS NULL
            ORDER BY parcel_id
        """)

    params = {"lim": limit} if limit else {}
    result = await session.execute(sql, params)
    rows = result.fetchall()
    return [r[0] for r in rows]


async def write_cama_result(
    session: AsyncSession,
    parcel_id: str,
    coerced: dict,
    raw_json: dict,
    dry_run: bool,
) -> None:
    """
    Upsert CAMA fields back onto the properties row for this parcel.
    Only overwrites a column if the parsed value is not None — never
    blanks out an existing NAL value with a None from a failed parse.
    """
    if dry_run:
        logger.info("[DRY-RUN] Would write CAMA for %s: %s", parcel_id, coerced)
        return

    # Build SET clause dynamically — only include non-None fields
    set_parts = []
    params: dict = {"parcel_id": parcel_id, "raw_cama_json": json.dumps(raw_json), "enriched_at": datetime.now(timezone.utc)}

    for col, val in coerced.items():
        if val is not None:
            set_parts.append(f"{col} = :{col}")
            params[col] = val

    set_parts.append("raw_cama_json = :raw_cama_json")
    set_parts.append("cama_enriched_at = :enriched_at")
    set_parts.append("updated_at = :enriched_at")

    sql = text(f"""
        UPDATE properties
        SET {', '.join(set_parts)}
        WHERE parcel_id = :parcel_id
    """)

    await session.execute(sql, params)
    await session.commit()


# ── HTTP fetch ────────────────────────────────────────────────────────────────

async def fetch_cama_page(
    client: httpx.AsyncClient,
    parcel_id: str,
) -> Optional[str]:
    """
    Fetch the CAMA detail page for a single parcel.
    Returns HTML string on success, None on failure.
    Retries once on transient errors (5xx, timeout).
    """
    url = CAMA_URL.format(parcel_id=parcel_id)
    for attempt in range(2):
        try:
            resp = await client.get(url, headers=HEADERS, timeout=15.0)
            if resp.status_code == 200:
                return resp.text
            elif resp.status_code == 404:
                logger.warning("Parcel %s — CAMA page not found (404)", parcel_id)
                return None
            else:
                logger.warning(
                    "Parcel %s — HTTP %s on attempt %d",
                    parcel_id, resp.status_code, attempt + 1,
                )
        except httpx.TimeoutException:
            logger.warning("Parcel %s — timeout on attempt %d", parcel_id, attempt + 1)
        except httpx.RequestError as exc:
            logger.warning("Parcel %s — request error: %s", parcel_id, exc)
            break  # Non-transient — do not retry
        if attempt == 0:
            await asyncio.sleep(3.0)  # Brief pause before retry

    return None


# ── main loop ─────────────────────────────────────────────────────────────────

async def run(
    limit: Optional[int],
    parcel: Optional[str],
    dry_run: bool,
    delay: float,
    force: bool,
) -> None:
    engine = create_async_engine(settings.database_url, echo=False)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with AsyncSessionLocal() as session:
        # Determine target parcel list
        if parcel:
            parcel_ids = [parcel]
            logger.info("Single-parcel mode: %s", parcel)
        else:
            parcel_ids = await fetch_qualified_parcel_ids(session, limit, force)
            logger.info(
                "Found %d MQI-qualified parcels to enrich%s",
                len(parcel_ids),
                " (force mode — including already enriched)" if force else "",
            )

        if not parcel_ids:
            logger.info("No parcels to process. Exiting.")
            return

        counters = {"fetched": 0, "parsed": 0, "written": 0, "failed": 0, "empty": 0}

        async with httpx.AsyncClient(follow_redirects=True) as client:
            for i, pid in enumerate(parcel_ids, start=1):
                logger.info("Processing %d/%d — parcel %s", i, len(parcel_ids), pid)

                html = await fetch_cama_page(client, pid)
                if html is None:
                    counters["failed"] += 1
                    continue
                counters["fetched"] += 1

                raw_fields = parse_cama_html(html, pid)
                if not raw_fields:
                    counters["empty"] += 1
                    # Still write raw_cama_json as empty dict so we know
                    # we attempted this parcel
                    await write_cama_result(session, pid, {}, {}, dry_run)
                    continue
                counters["parsed"] += 1

                coerced = coerce_cama_fields(raw_fields, pid)

                await write_cama_result(session, pid, coerced, raw_fields, dry_run)
                counters["written"] += 1

                logger.debug("Parcel %s → %s", pid, coerced)

                # Rate limiting — be a good citizen
                if i < len(parcel_ids):
                    await asyncio.sleep(delay)

        logger.info(
            "CAMA enrichment complete | fetched=%d parsed=%d written=%d "
            "failed=%d empty=%d",
            counters["fetched"],
            counters["parsed"],
            counters["written"],
            counters["failed"],
            counters["empty"],
        )

    await engine.dispose()


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download per-parcel CAMA data from ECPA for MQI-qualified properties."
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Maximum number of parcels to process (default: all)",
    )
    parser.add_argument(
        "--parcel", type=str, default=None,
        help="Process a single parcel ID (overrides --limit)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Fetch and parse but do not write to the database",
    )
    parser.add_argument(
        "--delay", type=float, default=2.0,
        help="Seconds to wait between requests (default: 2.0, minimum: 1.0)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-fetch parcels that already have cama_enriched_at set",
    )
    args = parser.parse_args()

    # Enforce minimum delay
    delay = max(args.delay, 1.0)
    if delay != args.delay:
        logger.warning("Delay below 1.0s is not permitted. Using 1.0s.")

    asyncio.run(run(
        limit=args.limit,
        parcel=args.parcel,
        dry_run=args.dry_run,
        delay=delay,
        force=args.force,
    ))


if __name__ == "__main__":
    main()
