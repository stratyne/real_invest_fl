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

Resumability: automatic via sales_history_enriched_at IS NULL filter.
--force flag re-processes all parcels regardless of stamp.

Upsert semantics: ON CONFLICT updates mutable fields (instrument_type,
qualification_code, sale_type, sale_price, multi_parcel,
price_per_sqft, source, scraped_at) when any differ. Immutable fields
that form the unique constraint key (sale_date, grantor, grantee) are
never updated.

source tag: srcpa_parcel (distinct from srcpa_parcelcard).
data_source_status source tag: santa_rosa_sales.

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
COUNTY_FIPS        = "12113"
SOURCE_NAME        = "srcpa_parcel"
DATA_SOURCE_STATUS = "santa_rosa_sales"
TARGET_DOR_UCS     = ["001"]

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

    # Not-found: parcelview returns a minimal page with remixContext
    # "empty":true and no salesContainer. Distinct from soft-block.
    if '"empty":true' in html and 'id="salesContainer"' not in html:
        logger.warning(
            "Parcel %s — not found on parcelview.srcpa.gov. Skipping.",
            parcel_id,
        )
        return base.NOT_FOUND

    # Soft-block: salesContainer absent but page is not a not-found
    # response — server is blocking or site structure has changed.
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

        cell_map: dict[str, str] = {}
        for td in cells:
            col_name = td["data-cell"]
            # Book / Page: no schema column — discard entirely.
            # Extracting text produces doubled content due to nested
            # <span> and <a> with identical text.
            if col_name == "Book / Page":
                continue
            cell_map[col_name] = td.get_text(strip=True)

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
    force: bool,
    limit: Optional[int],
) -> list[tuple[str, Optional[int]]]:
    """
    Fetch all Santa Rosa SFR parcels ordered by parcel_id.

    Returns list of (parcel_id, tot_lvg_area) tuples.
    tot_lvg_area is passed to coerce_sale() for price_per_sqft
    derivation.

    When force=False (default), skips parcels where
    sales_history_enriched_at IS NOT NULL — these have already been
    fully processed by a previous run.

    When force=True, fetches all parcels regardless of stamp — used
    for quarterly refresh runs to pick up new sales on all parcels.
    """
    uc_placeholders = ", ".join(f"'{uc}'" for uc in TARGET_DOR_UCS)

    force_clause = "" if force else "AND sales_history_enriched_at IS NULL"

    limit_clause = ""
    params: dict = {"fips": COUNTY_FIPS}

    if limit:
        limit_clause = "LIMIT :lim"
        params["lim"] = limit

    sql_str = f"""
        SELECT parcel_id, tot_lvg_area
        FROM properties
        WHERE county_fips = :fips
          AND dor_uc IN ({uc_placeholders})
          {force_clause}
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
        multi_parcel, price_per_sqft, source, scraped_at.

    scraped_at is always updated on conflict — it reflects the most
    recent scrape that touched the row, regardless of whether data
    changed.

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
            source             = EXCLUDED.source,
            scraped_at         = now()
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


async def stamp_parcel(
    session: AsyncSession,
    parcel_id: str,
    now: datetime,
    dry_run: bool,
) -> None:
    """
    Stamp sales_history_enriched_at on the properties row for this
    parcel after successful processing.

    Written regardless of whether the parcel had any sale rows —
    a parcel with no sales is still fully processed and should be
    excluded from future runs unless --force is passed.
    """
    if dry_run:
        logger.debug("[DRY-RUN] stamp sales_history_enriched_at for %s", parcel_id)
        return

    await session.execute(
        text(
            "UPDATE properties "
            "SET sales_history_enriched_at = :now, "
            "    updated_at = :now "
            "WHERE county_fips = :fips "
            "AND parcel_id = :pid"
        ),
        {"now": now, "fips": COUNTY_FIPS, "pid": parcel_id},
    )
    await session.commit()


async def update_data_source_status(
    session: AsyncSession,
    status: str,
    record_count: int,
    error_message: Optional[str],
    dry_run: bool,
) -> None:
    """
    Upsert a row in data_source_status for this pipeline run.

    source = 'santa_rosa_sales' (pipeline identifier).
    county_fips = '12113'.
    status: 'SUCCESS' | 'PARTIAL' | 'FAILED'.

    Called once at the end of every run — soft-block stops report
    PARTIAL, clean completions report SUCCESS.
    """
    if dry_run:
        logger.info(
            "[DRY-RUN] data_source_status: source=%s status=%s count=%d",
            DATA_SOURCE_STATUS, status, record_count,
        )
        return

    now = datetime.now(timezone.utc)
    last_success_at = now if status == "SUCCESS" else None

    await session.execute(
        text("""
            INSERT INTO data_source_status (
                source, county_fips, display_name,
                last_run_at, last_success_at,
                last_run_status, last_record_count,
                last_error_message,
                created_at, updated_at
            ) VALUES (
                :source, :fips, :display_name,
                :now, :last_success_at,
                :status, :count,
                :error,
                :now, :now
            )
            ON CONFLICT (source, county_fips)
            DO UPDATE SET
                last_run_at        = EXCLUDED.last_run_at,
                last_success_at    = CASE
                    WHEN EXCLUDED.last_run_status = 'SUCCESS'
                    THEN EXCLUDED.last_run_at
                    ELSE data_source_status.last_success_at
                END,
                last_run_status    = EXCLUDED.last_run_status,
                last_record_count  = EXCLUDED.last_record_count,
                last_error_message = EXCLUDED.last_error_message,
                updated_at         = EXCLUDED.updated_at
        """),
        {
            "source":          DATA_SOURCE_STATUS,
            "fips":            COUNTY_FIPS,
            "display_name":    "Santa Rosa Sale History (parcelview.srcpa.gov)",
            "now":             now,
            "last_success_at": last_success_at,
            "status":          status,
            "count":           record_count,
            "error":           error_message,
        },
    )
    await session.commit()


# ── main run loop ─────────────────────────────────────────────────────────────

async def run(
    force: bool,
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
        5. Stamp sales_history_enriched_at on properties
        6. Rate-limit before next request

    On completion (clean or soft-block), stamps data_source_status.
    """
    engine = create_async_engine(settings.host_database_url, echo=False)
    AsyncSessionLocal = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with AsyncSessionLocal() as session:
        if parcel:
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
            parcels = await fetch_all_parcels(session, force, limit)
            logger.info(
                "Found %d Santa Rosa SFR parcels to process%s",
                len(parcels),
                " (force mode — all parcels)" if force else "",
            )

    if not parcels:
        logger.info("No parcels to process. Exiting.")
        await engine.dispose()
        return

    counters = {
        "fetched":        0,
        "soft_blocked":   0,
        "not_found":      0,
        "failed":         0,
        "sales_affected": 0,
    }
    soft_blocked = False

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
            now = datetime.now(timezone.utc)

            for i, (pid, tot_lvg_area) in enumerate(parcels, start=1):
                logger.info("Processing %d/%d — parcel %s", i, total, pid)

                html = await fetch_page(client, pid)

                if html is base.SOFT_BLOCK or html == base.SOFT_BLOCK:
                    counters["soft_blocked"] += 1
                    soft_blocked = True
                    logger.error(
                        "Soft block on parcel %s at position %d/%d. "
                        "Re-run without --resume-from — automatic "
                        "resumption via sales_history_enriched_at.",
                        pid, i, total,
                    )
                    break

                if html is base.NOT_FOUND or html == base.NOT_FOUND:
                    counters["not_found"] += 1
                    logger.warning("Parcel %s — not found, stamping and continuing.", pid)
                    await stamp_parcel(session, pid, now, dry_run)
                    if i < total:
                        await asyncio.sleep(random.uniform(delay, delay_max))
                    continue

                if html is None:
                    counters["failed"] += 1
                    if i < total:
                        await asyncio.sleep(random.uniform(delay, delay_max))
                    continue

                counters["fetched"] += 1

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

                # Stamp this parcel as fully processed — skipped on next
                # run unless --force is passed.
                await stamp_parcel(session, pid, now, dry_run)

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

    # ── data_source_status stamp ──────────────────────────────────────────
    run_status = "PARTIAL" if soft_blocked else "SUCCESS"
    error_msg = (
        "Run stopped on soft-block. Re-run to continue." if soft_blocked
        else None
    )
    async with AsyncSessionLocal() as status_session:
        await update_data_source_status(
            status_session,
            status=run_status,
            record_count=counters["sales_affected"],
            error_message=error_msg,
            dry_run=dry_run,
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
        "--force",
        action="store_true",
        help=(
            "Re-process all parcels regardless of sales_history_enriched_at. "
            "Use for quarterly refresh runs to pick up new sales on all parcels."
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
        help="Process a single parcel ID (overrides --force and --limit).",
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
        force=args.force,
        limit=args.limit,
        parcel=args.parcel,
        dry_run=args.dry_run,
        delay=args.delay,
        delay_max=args.delay_max,
    ))


if __name__ == "__main__":
    main()
