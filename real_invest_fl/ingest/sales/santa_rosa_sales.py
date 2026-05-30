"""
real_invest_fl/ingest/sales/santa_rosa_sales.py
------------------------------------------------
Santa Rosa County full sale history scraper.

Source: https://parcelview.srcpa.gov/?parcel={parcel_id}&baseUrl=http://srcpa.gov/
Technology: Remix/React SSR application, server-rendered HTML.
            Plain httpx GET with browser-mimicking headers.
            No JavaScript rendering required.

Parse target: <div id="salesContainer"> table.
Each <td> carries data-cell="<column name>" — used as the column
selector. No positional index logic.

Soft-block detection: id="salesContainer" absent from response body.
Not-found detection: salesContainer present, zero <td> data cells.

Target: all Santa Rosa SFR parcels (dor_uc = '001'), 68,312 parcels.
Does NOT gate on cama_enriched_at — sale history completeness is
independent of building enrichment.

Resumability: --resume-from <parcel_id> CLI arg. Fetches full ordered
parcel list, skips all IDs strictly less than the supplied value.

Upsert semantics: ON CONFLICT updates mutable fields (instrument_type,
qualification_code, sale_type, sale_price, multi_parcel,
price_per_sqft, source) when any differ. Immutable fields that form the
unique constraint key (sale_date, grantor, grantee) are never updated.

source tag: srcpa_parcel (distinct from srcpa_parcelcard).

This scraper does NOT use base.run() — it has its own lightweight loop.
It does NOT call write_cama() or coerce_building().
It DOES use coerce_sale() from base.py unchanged.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# ── path bootstrap ─────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import settings                          # noqa: E402
from real_invest_fl.ingest.cama import base                  # noqa: E402

# ── logging ───────────────────────────────────────────────────────────────────
logger = logging.getLogger("sales.santa_rosa")

# ── constants ─────────────────────────────────────────────────────────────────
COUNTY_FIPS  = "12113"
SOURCE_NAME  = "srcpa_parcel"
TARGET_DOR_UCS = ["001"]

DEFAULT_DELAY     = 1.0
DEFAULT_DELAY_MAX = 3.0
REST_EVERY        = 500
REST_SECONDS      = 300.0

BASE_URL = "https://parcelview.srcpa.gov/?parcel={parcel_id}&baseUrl=http://srcpa.gov/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# ── HTTP fetch ────────────────────────────────────────────────────────────────

async def fetch_page(
    client: httpx.AsyncClient,
    parcel_id: str,
) -> Optional[str]:
    url = BASE_URL.format(parcel_id=parcel_id)
    try:
        response = await client.get(url, timeout=30.0)
    except (httpx.TimeoutException, httpx.RequestError) as exc:
        logger.warning("Parcel %s — request error: %s", parcel_id, exc)
        return None

    if response.status_code != 200:
        logger.warning(
            "Parcel %s — HTTP %d", parcel_id, response.status_code
        )
        return None

    html = response.text

    if 'id="salesContainer"' not in html:
        logger.error(
            "Parcel %s — salesContainer absent. Soft-block or site "
            "structural change detected. Stopping run.",
            parcel_id,
        )
        return base.SOFT_BLOCK

    return html


# ── parse ─────────────────────────────────────────────────────────────────────

def parse_sales(html: str, parcel_id: str) -> list[dict]:
    """
    Parse all sale rows from the salesContainer table.

    Column values are read by data-cell attribute name — no positional
    index logic. Book / Page is parsed and discarded (no schema column).

    Returns an empty list for parcels with no sale history rows.
    Returns a list of raw dicts (string values) for coerce_sale().

    HTML entity decoding (&amp; → &) is handled automatically by
    BeautifulSoup.
    """
    soup = BeautifulSoup(html, "html.parser")
    container = soup.find("div", id="salesContainer")

    if container is None:
        # Should not reach here — fetch_page() guards against this —
        # but be defensive.
        logger.warning("Parcel %s — salesContainer not found in parse", parcel_id)
        return []

    # Data rows are <tr role="row"> that contain <td> elements.
    # The header row contains <th> elements — skip it by checking for <td>.
    data_rows = [
        tr for tr in container.find_all("tr", role="row")
        if tr.find("td") is not None
    ]

    if not data_rows:
        logger.debug("Parcel %s — no sale history rows", parcel_id)
        return []

    sales: list[dict] = []

    for tr in data_rows:
        cells = tr.find_all("td", attrs={"data-cell": True})

        # Index by data-cell attribute for robust column mapping.
        cell_map: dict[str, str] = {}
        for td in cells:
            col_name = td["data-cell"]
            # Book / Page cell contains nested <span> and <a> with
            # duplicated text. We discard it entirely — no schema
            # column exists for it. Extracting its text would produce
            # doubled content (e.g. "4523 / 10554523 / 1055").
            if col_name == "Book / Page":
                continue
            cell_map[col_name] = td.get_text(strip=True)

        # sale_date is required — skip row silently if absent.
        if not cell_map.get("Sale Date"):
            logger.debug(
                "Parcel %s — row missing Sale Date, skipping", parcel_id
            )
            continue

        sales.append({
            "sale_date":          cell_map.get("Sale Date", ""),
            "sale_price":         cell_map.get("Sale Price", ""),
            "instrument_type":    cell_map.get("Instrument", ""),
            "qualification_code": cell_map.get("Qualification", ""),
            "sale_type":          cell_map.get("Sale Type", ""),
            "multi_parcel":       cell_map.get("Multi-Parcel", ""),
            "grantor":            cell_map.get("Grantor", ""),
            "grantee":            cell_map.get("Grantee", ""),
        })

    logger.debug("Parcel %s — parsed %d sale rows", parcel_id, len(sales))
    return sales


# ── database helpers ──────────────────────────────────────────────────────────

async def fetch_all_parcels(
    session: AsyncSession,
    resume_from: Optional[str],
    limit: Optional[int],
) -> list[tuple[str, Optional[int]]]:
    """
    Fetch all Santa Rosa SFR parcels ordered by parcel_id.

    Returns list of (parcel_id, tot_lvg_area) tuples.
    tot_lvg_area is passed to coerce_sale() for price_per_sqft
    derivation.

    resume_from: if supplied, skips all parcel_ids strictly less than
    this value. The comparison is lexicographic — valid because Santa
    Rosa parcel IDs are fixed-format strings with consistent ordering.
    """
    uc_placeholders = ", ".join(f"'{uc}'" for uc in TARGET_DOR_UCS)

    resume_clause = ""
    params: dict = {"fips": COUNTY_FIPS}

    if resume_from:
        resume_clause = "AND parcel_id >= :resume_from"
        params["resume_from"] = resume_from

    limit_clause = ""
    if limit:
        limit_clause = "LIMIT :lim"
        params["lim"] = limit

    sql_str = f"""
        SELECT parcel_id, tot_lvg_area
        FROM properties
        WHERE county_fips = :fips
          AND dor_uc IN ({uc_placeholders})
          {resume_clause}
        ORDER BY parcel_id
        {limit_clause}
    """

    result = await session.execute(text(sql_str), params)
    return [(row[0], row[1]) for row in result.fetchall()]


async def write_sales_upsert(
    session: AsyncSession,
    sales: list[dict],
    dry_run: bool,
) -> int:
    """
    Upsert sale history rows into parcel_sale_history.

    ON CONFLICT (uq_psh_county_parcel_sale) — key is
    (county_fips, parcel_id, sale_date, grantor, grantee).

    Mutable fields updated on conflict when any differ:
        instrument_type, qualification_code, sale_type, sale_price,
        multi_parcel, price_per_sqft, source.

    Immutable fields (part of unique key) are never updated:
        sale_date, grantor, grantee.

    Returns count of rows inserted or updated.
    """
    if not sales:
        return 0

    if dry_run:
        for s in sales:
            logger.info("[DRY-RUN] Sale upsert: %s", s)
        return 0

    sql = text("""
        INSERT INTO parcel_sale_history (
            county_fips, parcel_id, sale_date, sale_price,
            instrument_type, qualification_code, sale_type,
            multi_parcel, grantor, grantee, price_per_sqft, source
        ) VALUES (
            :county_fips, :parcel_id, :sale_date, :sale_price,
            :instrument_type, :qualification_code, :sale_type,
            :multi_parcel, :grantor, :grantee, :price_per_sqft, :source
        )
        ON CONFLICT ON CONSTRAINT uq_psh_county_parcel_sale
        DO UPDATE SET
            instrument_type    = EXCLUDED.instrument_type,
            qualification_code = EXCLUDED.qualification_code,
            sale_type          = EXCLUDED.sale_type,
            sale_price         = EXCLUDED.sale_price,
            multi_parcel       = EXCLUDED.multi_parcel,
            price_per_sqft     = EXCLUDED.price_per_sqft,
            source             = EXCLUDED.source
        WHERE
            parcel_sale_history.instrument_type
                IS DISTINCT FROM EXCLUDED.instrument_type
            OR parcel_sale_history.qualification_code
                IS DISTINCT FROM EXCLUDED.qualification_code
            OR parcel_sale_history.sale_type
                IS DISTINCT FROM EXCLUDED.sale_type
            OR parcel_sale_history.sale_price
                IS DISTINCT FROM EXCLUDED.sale_price
    """)

    affected = 0
    for sale in sales:
        result = await session.execute(sql, sale)
        affected += result.rowcount

    await session.commit()
    return affected


# ── main run loop ─────────────────────────────────────────────────────────────

async def run(
    resume_from: Optional[str],
    limit: Optional[int],
    parcel: Optional[str],
    dry_run: bool,
    delay: float,
    delay_max: float,
) -> None:
    """
    Main processing loop for Santa Rosa full sale history scraper.

    For each qualifying parcel:
        1. Fetch parcelview.srcpa.gov page via fetch_page()
        2. Parse all sale rows via parse_sales()
        3. Coerce each row via base.coerce_sale()
        4. Upsert into parcel_sale_history via write_sales_upsert()
        5. Rate-limit before next request
    """
    engine = create_async_engine(settings.host_database_url, echo=False)
    AsyncSessionLocal = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with AsyncSessionLocal() as session:
        if parcel:
            # Single-parcel mode: query tot_lvg_area for this one parcel.
            result = await session.execute(
                text(
                    "SELECT parcel_id, tot_lvg_area FROM properties "
                    "WHERE county_fips = :fips AND parcel_id = :pid"
                ),
                {"fips": COUNTY_FIPS, "pid": parcel},
            )
            row = result.fetchone()
            if row is None:
                logger.error(
                    "Parcel %s not found in DB for county %s",
                    parcel, COUNTY_FIPS,
                )
                await engine.dispose()
                return
            parcels: list[tuple[str, Optional[int]]] = [(row[0], row[1])]
            logger.info("Single-parcel mode: %s", parcel)
        else:
            parcels = await fetch_all_parcels(session, resume_from, limit)
            logger.info(
                "Found %d Santa Rosa SFR parcels to process%s",
                len(parcels),
                f" (resuming from {resume_from})" if resume_from else "",
            )

    if not parcels:
        logger.info("No parcels to process. Exiting.")
        await engine.dispose()
        return

    counters = {
        "fetched":       0,
        "soft_blocked":  0,
        "not_found":     0,
        "failed":        0,
        "sales_affected": 0,
    }

    async with AsyncSessionLocal() as session:
        async with httpx.AsyncClient(
            follow_redirects=True,
            limits=httpx.Limits(
                max_keepalive_connections=0,
                max_connections=1,
            ),
            headers=HEADERS,
        ) as client:
            total = len(parcels)
            for i, (pid, tot_lvg_area) in enumerate(parcels, start=1):
                logger.info("Processing %d/%d — parcel %s", i, total, pid)

                html = await fetch_page(client, pid)

                if html is base.SOFT_BLOCK or html == base.SOFT_BLOCK:
                    counters["soft_blocked"] += 1
                    logger.error(
                        "Soft block on parcel %s at position %d/%d. "
                        "Re-run with --resume-from %s",
                        pid, i, total, pid,
                    )
                    break

                if html is None:
                    counters["failed"] += 1
                    # Transient failure — parcel remains in queue.
                    # Apply delay before continuing.
                    if i < total:
                        await asyncio.sleep(random.uniform(delay, delay_max))
                    continue

                counters["fetched"] += 1

                # Not-found: salesContainer present (fetch_page passed)
                # but no data rows. coerce_sale() will receive an empty
                # list — write_sales_upsert() is a no-op. No special
                # handling needed — parse_sales() returns [] cleanly.
                raw_sales = parse_sales(html, pid)

                if not raw_sales:
                    counters["not_found"] += 1
                    logger.debug("Parcel %s — no sale rows found", pid)
                else:
                    coerced_sales: list[dict] = []
                    for raw_sale in raw_sales:
                        coerced = base.coerce_sale(
                            raw_sale,
                            pid,
                            COUNTY_FIPS,
                            SOURCE_NAME,
                            tot_lvg_area,
                        )
                        if coerced is not None:
                            coerced_sales.append(coerced)

                    affected = await write_sales_upsert(
                        session, coerced_sales, dry_run
                    )
                    counters["sales_affected"] += affected

                    logger.debug(
                        "Parcel %s — %d raw / %d coerced / %d upserted",
                        pid,
                        len(raw_sales),
                        len(coerced_sales),
                        affected,
                    )

                # ── Rate limiting ──────────────────────────────────── #
                if i < total:
                    await asyncio.sleep(random.uniform(delay, delay_max))

                    if REST_EVERY and i % REST_EVERY == 0:
                        logger.info(
                            "Reached parcel %d — resting %.1fs.",
                            i, REST_SECONDS,
                        )
                        await asyncio.sleep(REST_SECONDS)

    logger.info(
        "Sale history run complete | county=%s fetched=%d "
        "soft_blocked=%d not_found=%d failed=%d sales_affected=%d",
        COUNTY_FIPS,
        counters["fetched"],
        counters["soft_blocked"],
        counters["not_found"],
        counters["failed"],
        counters["sales_affected"],
    )

    await engine.dispose()


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description=(
            "Santa Rosa County full sale history scraper. "
            "Source: parcelview.srcpa.gov"
        )
    )
    parser.add_argument(
        "--resume-from",
        type=str,
        default=None,
        metavar="PARCEL_ID",
        help=(
            "Skip all parcel_ids strictly less than this value. "
            "Use the last-logged parcel_id after a soft-block stop."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of parcels to process (default: all).",
    )
    parser.add_argument(
        "--parcel",
        type=str,
        default=None,
        help="Process a single parcel ID (overrides --resume-from and --limit).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and parse but do not write to the database.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY,
        help=f"Lower bound of per-request delay in seconds (default: {DEFAULT_DELAY}).",
    )
    parser.add_argument(
        "--delay-max",
        type=float,
        default=DEFAULT_DELAY_MAX,
        help=f"Upper bound of per-request delay in seconds (default: {DEFAULT_DELAY_MAX}).",
    )
    args = parser.parse_args()

    if args.delay_max < args.delay:
        logger.warning(
            "--delay-max (%.2f) is below --delay (%.2f); raising to match.",
            args.delay_max, args.delay,
        )
        args.delay_max = args.delay

    logger.info(
        "Per-request delay range: %.2fs – %.2fs (uniform random)",
        args.delay, args.delay_max,
    )

    asyncio.run(run(
        resume_from=args.resume_from,
        limit=args.limit,
        parcel=args.parcel,
        dry_run=args.dry_run,
        delay=args.delay,
        delay_max=args.delay_max,
    ))


if __name__ == "__main__":
    main()
