"""
real_invest_fl/ingest/cama/base.py
------------------------------------
Shared CAMA + sale history ingest framework.

County-specific modules (escambia.py, santa_rosa.py, etc.) provide:
    COUNTY_FIPS       str
    SOURCE_NAME       str
    HEADERS           dict  — HTTP request headers

    async fetch_page(client, parcel_id) -> Optional[str] | SOFT_BLOCK
    parse_building(html, parcel_id)    -> dict
    parse_sales(html, parcel_id)       -> list[dict]

This module provides everything else:
    coerce_building()
    coerce_sale()
    fetch_qualified_parcels()
    write_cama()
    write_sales()
    run()
    main()

County modules call base.main() as their entry point, passing all
county-specific values including rate-limiting parameters. No
rate-limiting defaults are assumed in base.py — every county module
must declare its own values explicitly.

Convention: every county module ends with:

    if __name__ == "__main__":
        base.main(
            county_fips=COUNTY_FIPS,
            source_name=SOURCE_NAME,
            fetch_page_fn=fetch_page,
            parse_building_fn=parse_building,
            parse_sales_fn=parse_sales,
            headers=HEADERS,
            target_dor_ucs=TARGET_DOR_UCS,
            default_delay=DEFAULT_DELAY,
            default_delay_max=DEFAULT_DELAY_MAX,
            rest_every=REST_EVERY,
            rest_seconds=REST_SECONDS,
        )
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import re
import sys
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Optional

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# ── path bootstrap ────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import settings  # noqa: E402

# ── logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("cama.base")

# ── sentinel ──────────────────────────────────────────────────────────────────
SOFT_BLOCK = "__SOFT_BLOCK__"


# ── coercion ──────────────────────────────────────────────────────────────────

def coerce_building(raw: dict, parcel_id: str) -> tuple[dict, set[str]]:
    """
    Coerce raw string values from a county parse_building() into typed
    Python values ready for the properties table columns.

    Input keys (all optional, all strings):
        exterior_wall, roof_type, foundation, living_area,
        bedrooms, bathrooms, act_yr_blt, eff_yr_blt, zoning,
        quality_code, condition_code

    Returns (coerced, null_cols) where:
        coerced   — dict of column_name → typed value
        null_cols — set of column names explicitly rejected by a sanity
                    guard; write_cama() will write NULL for these columns
                    regardless of existing DB value.
    """
    def _int(val: str) -> Optional[int]:
        if not val:
            return None
        digits = re.sub(r"[^\d]", "", str(val))
        return int(digits) if digits else None

    def _decimal(val: str) -> Optional[float]:
        if not val:
            return None
        cleaned = re.sub(r"[^\d.]", "", str(val))
        try:
            return float(cleaned)
        except ValueError:
            return None

    def _str(val: str, max_len: int) -> Optional[str]:
        if not val:
            return None
        s = str(val).strip()
        return s[:max_len] if s else None

    null_cols: set[str] = set()

    act_yr_blt  = _int(raw.get("act_yr_blt", ""))
    eff_yr_blt  = _int(raw.get("eff_yr_blt", ""))
    living_area = _int(raw.get("living_area", ""))
    bedrooms    = _int(raw.get("bedrooms", ""))
    bathrooms   = _decimal(raw.get("bathrooms", ""))

    current_year = datetime.now().year

    if act_yr_blt and not (1800 <= act_yr_blt <= current_year):
        logger.warning("Parcel %s — suspicious act_yr_blt: %s", parcel_id, act_yr_blt)
        act_yr_blt = None
        null_cols.add("act_yr_blt")

    if living_area is not None and living_area <= 0:
        logger.warning("Parcel %s — tot_lvg_area %s <= 0, treating as None", parcel_id, living_area)
        living_area = None
        null_cols.add("tot_lvg_area")

    if bedrooms is not None and bedrooms <= 0:
        logger.warning("Parcel %s — bedrooms %s <= 0, treating as None", parcel_id, bedrooms)
        bedrooms = None
        null_cols.add("bedrooms")

    if bedrooms is not None and not (1 <= bedrooms <= 20):
        logger.warning("Parcel %s — suspicious bedrooms: %s", parcel_id, bedrooms)
        bedrooms = None
        null_cols.add("bedrooms")

    if bathrooms is not None and bathrooms <= 0.0:
        logger.warning("Parcel %s — bathrooms %s <= 0, treating as None", parcel_id, bathrooms)
        bathrooms = None
        null_cols.add("bathrooms")

    if bathrooms is not None and not (0.5 <= bathrooms <= 20.0):
        logger.warning("Parcel %s — suspicious bathrooms: %s", parcel_id, bathrooms)
        bathrooms = None
        null_cols.add("bathrooms")

    return {
        "exterior_wall":       _str(raw.get("exterior_wall", ""), 100),
        "roof_type":           _str(raw.get("roof_type", ""), 100),
        "foundation_type":     _str(raw.get("foundation", ""), 100),
        "tot_lvg_area":        living_area,
        "bedrooms":            bedrooms,
        "bathrooms":           bathrooms,
        "act_yr_blt":          act_yr_blt,
        "eff_yr_blt":          eff_yr_blt,
        "zoning":              _str(raw.get("zoning", ""), 20),
        "cama_quality_code":   _str(raw.get("quality_code", ""), 10),
        "cama_condition_code": _str(raw.get("condition_code", ""), 10),
    }, null_cols


def coerce_sale(
    raw: dict,
    parcel_id: str,
    county_fips: str,
    source_name: str,
    tot_lvg_area: Optional[int],
) -> Optional[dict]:
    """
    Coerce a single raw sale dict from a county parse_sales() into typed
    values ready for the parcel_sale_history table.

    Expected raw keys (all strings):
        sale_date, sale_price, instrument_type, qualification_code,
        sale_type, multi_parcel, grantor, grantee

    sale_date is required. Returns None if absent or unparseable.
    tot_lvg_area is used to derive price_per_sqft at ingest time.
    """
    sale_date_str = raw.get("sale_date", "").strip()
    sale_date: Optional[date] = None
    if sale_date_str:
        try:
            sale_date = datetime.strptime(sale_date_str, "%m/%d/%Y").date()
        except ValueError:
            logger.warning(
                "Parcel %s — unparseable sale_date: %s",
                parcel_id, sale_date_str,
            )
            return None

    if sale_date is None:
        return None

    price_str = re.sub(r"[^\d]", "", raw.get("sale_price", ""))
    sale_price: Optional[int] = int(price_str) if price_str else None

    price_per_sqft: Optional[Decimal] = None
    if sale_price and sale_price > 0 and tot_lvg_area and tot_lvg_area > 0:
        try:
            price_per_sqft = round(
                Decimal(sale_price) / Decimal(tot_lvg_area), 2
            )
        except InvalidOperation:
            pass

    multi_raw = raw.get("multi_parcel", "").strip().upper()
    multi_parcel = multi_raw not in ("N", "")

    def _str(val: str, max_len: int) -> Optional[str]:
        s = str(val).strip() if val else ""
        return s[:max_len] if s else None

    return {
        "county_fips":        county_fips,
        "parcel_id":          parcel_id,
        "sale_date":          sale_date,
        "sale_price":         sale_price,
        "instrument_type":    _str(raw.get("instrument_type", ""), 10),
        "qualification_code": _str(raw.get("qualification_code", ""), 5),
        "sale_type":          _str(raw.get("sale_type", ""), 5),
        "multi_parcel":       multi_parcel,
        "grantor":            (_str(raw.get("grantor", ""), 300) or ""),
        "grantee":            (_str(raw.get("grantee", ""), 300) or ""),
        "price_per_sqft":     price_per_sqft,
        "source":             source_name,
    }


# ── database helpers ──────────────────────────────────────────────────────────

async def fetch_qualified_parcels(
    session: AsyncSession,
    county_fips: str,
    target_dor_ucs: list[str],
    limit: Optional[int],
    force: bool,
) -> list[str]:
    """
    Return parcel_id values for parcels matching target_dor_ucs in the
    given county that require CAMA enrichment.

    target_dor_ucs is supplied by the county module — e.g. ['001'] for
    single-family only, or ['001', '002'] to include mobile homes.

    Skips parcels where cama_enriched_at IS NOT NULL unless force=True.
    """
    placeholders = ", ".join(f"'{uc}'" for uc in target_dor_ucs)
    uc_clause = f"dor_uc IN ({placeholders})"

    if force:
        where = f"WHERE county_fips = :fips AND {uc_clause}"
    else:
        where = (
            f"WHERE county_fips = :fips "
            f"AND {uc_clause} "
            f"AND cama_enriched_at IS NULL"
        )

    limit_clause = "LIMIT :lim" if limit else ""

    sql_str = f"""
        SELECT parcel_id
        FROM properties
        {where}
        ORDER BY parcel_id
        {limit_clause}
    """

    params: dict = {"fips": county_fips}
    if limit:
        params["lim"] = limit

    result = await session.execute(text(sql_str), params)
    return [r[0] for r in result.fetchall()]


async def write_cama(
    session: AsyncSession,
    county_fips: str,
    parcel_id: str,
    coerced: dict,
    null_cols: set[str],
    raw_fields: dict,
    dry_run: bool,
) -> None:
    """
    Write CAMA fields back to the properties table for this parcel.

    Only writes non-None values from coerced — never overwrites an
    existing DB value with None from a failed parse.

    Always writes raw_cama_json and cama_enriched_at regardless of
    whether any CAMA fields parsed successfully.

    Explicitly writes NULL for columns in null_cols — these were present
    in source data but rejected by a sanity guard in coerce_building().
    """
    if dry_run:
        logger.info("[DRY-RUN] CAMA for %s | %s", parcel_id, coerced)
        if null_cols:
            logger.info(
                "[DRY-RUN] Explicit NULL cols for %s | %s",
                parcel_id, null_cols,
            )
        return

    now = datetime.now(timezone.utc)

    set_parts = [
        "raw_cama_json = :raw_cama_json",
        "cama_enriched_at = :enriched_at",
        "updated_at = :enriched_at",
    ]
    params: dict = {
        "county_fips":   county_fips,
        "parcel_id":     parcel_id,
        "raw_cama_json": json.dumps(raw_fields),
        "enriched_at":   now,
    }

    for col, val in coerced.items():
        if val is not None:
            set_parts.append(f"{col} = :{col}")
            params[col] = val

    for col in null_cols:
        if col not in params:
            set_parts.append(f"{col} = NULL")            

    await session.execute(
        text(
            f"UPDATE properties "
            f"SET {', '.join(set_parts)} "
            f"WHERE county_fips = :county_fips "
            f"AND parcel_id = :parcel_id"
        ),
        params,
    )
    await session.commit()


async def write_sales(
    session: AsyncSession,
    sales: list[dict],
    dry_run: bool,
) -> int:
    """
    Upsert sale history rows into parcel_sale_history.

    Uses INSERT ... ON CONFLICT DO NOTHING against the unique constraint
    uq_psh_county_parcel_sale (county_fips, parcel_id, sale_date,
    grantor, grantee). Re-running is safe — existing rows are unchanged.

    Returns count of rows actually inserted (0 on conflict).
    """
    if not sales:
        return 0

    if dry_run:
        for s in sales:
            logger.info("[DRY-RUN] Sale: %s", s)
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
        DO NOTHING
    """)

    inserted = 0
    for sale in sales:
        result = await session.execute(sql, sale)
        inserted += result.rowcount

    await session.commit()
    return inserted


# ── main run loop ─────────────────────────────────────────────────────────────

async def run(
    county_fips: str,
    source_name: str,
    fetch_page_fn: Callable,
    parse_building_fn: Callable,
    parse_sales_fn: Callable,
    headers: dict,
    target_dor_ucs: list[str],
    limit: Optional[int],
    parcel: Optional[str],
    dry_run: bool,
    delay: float,
    delay_max: float,
    force: bool,
    rest_every: Optional[int],
    rest_seconds: float,
) -> None:
    """
    Main processing loop. Shared across all county CAMA scrapers.

    For each qualifying parcel:
        1. Fetch the county PA page via fetch_page_fn()
        2. Parse building characteristics via parse_building_fn()
        3. Parse sale history via parse_sales_fn()
        4. Coerce both to typed values
        5. Write CAMA fields to properties
        6. Write sale rows to parcel_sale_history
        7. Rate-limit before next request
    """
    engine = create_async_engine(settings.database_url, echo=False)
    AsyncSessionLocal = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with AsyncSessionLocal() as session:
        if parcel:
            parcel_ids = [parcel]
            logger.info("Single-parcel mode: %s", parcel)
        else:
            parcel_ids = await fetch_qualified_parcels(
                session, county_fips, target_dor_ucs, limit, force
            )
            logger.info(
                "Found %d parcels (dor_uc in %s) for county %s%s",
                len(parcel_ids),
                target_dor_ucs,
                county_fips,
                " (force mode)" if force else "",
            )

        if not parcel_ids:
            logger.info("No parcels to process. Exiting.")
            await engine.dispose()
            return

        counters = {
            "fetched":        0,
            "cama_written":   0,
            "cama_empty":     0,
            "sales_inserted": 0,
            "failed":         0,
        }

        async with httpx.AsyncClient(
            follow_redirects=True,
            limits=httpx.Limits(
                max_keepalive_connections=0,
                max_connections=1,
            ),
            headers=headers,
        ) as client:
            for i, pid in enumerate(parcel_ids, start=1):
                logger.info("Processing %d/%d — parcel %s", i, len(parcel_ids), pid)

                html = await fetch_page_fn(client, pid)

                if html is SOFT_BLOCK or html == SOFT_BLOCK:
                    counters["failed"] += 1
                    logger.error(
                        "Soft block on parcel %s — stopping. "
                        "Wait before re-running.",
                        pid,
                    )
                    break

                if html is None:
                    counters["failed"] += 1
                    continue

                counters["fetched"] += 1

                # ── CAMA ──────────────────────────────────────────────── #
                raw_building = parse_building_fn(html, pid)
                coerced, null_cols = coerce_building(raw_building, pid)

                if not raw_building:
                    counters["cama_empty"] += 1

                await write_cama(
                    session, county_fips, pid, coerced, null_cols, raw_building, dry_run
                )
                counters["cama_written"] += 1

                # ── Sales history ──────────────────────────────────────── #
                raw_sales = parse_sales_fn(html, pid)
                tot_lvg_area = coerced.get("tot_lvg_area")
                coerced_sales = []

                for raw_sale in raw_sales:
                    coerced_sale = coerce_sale(
                        raw_sale, pid, county_fips, source_name, tot_lvg_area
                    )
                    if coerced_sale:
                        coerced_sales.append(coerced_sale)

                inserted = await write_sales(session, coerced_sales, dry_run)
                counters["sales_inserted"] += inserted

                if raw_sales:
                    logger.debug(
                        "Parcel %s — %d sales found, %d inserted",
                        pid, len(raw_sales), inserted,
                    )

                # ── Rate limiting ──────────────────────────────────────── #
                if i < len(parcel_ids):
                    sleep_for = random.uniform(delay, delay_max)
                    await asyncio.sleep(sleep_for)

                    if rest_every and i % rest_every == 0:
                        logger.info(
                            "Reached parcel %d — resting %.1fs.",
                            i, rest_seconds,
                        )
                        await asyncio.sleep(rest_seconds)

    logger.info(
        "CAMA run complete | county=%s fetched=%d cama_written=%d "
        "cama_empty=%d sales_inserted=%d failed=%d",
        county_fips,
        counters["fetched"],
        counters["cama_written"],
        counters["cama_empty"],
        counters["sales_inserted"],
        counters["failed"],
    )

    await engine.dispose()


# ── CLI ───────────────────────────────────────────────────────────────────────

def main(
    county_fips: str,
    source_name: str,
    fetch_page_fn: Callable,
    parse_building_fn: Callable,
    parse_sales_fn: Callable,
    headers: dict,
    target_dor_ucs: list[str],
    default_delay: float,
    default_delay_max: float,
    rest_every: Optional[int],
    rest_seconds: float,
) -> None:
    """
    Shared CLI entry point for all county CAMA scrapers.

    All rate-limiting parameters are supplied by the county module.
    No defaults are assumed here — each county must declare its own
    values based on its PA site's behavior and robots.txt directives.

    County modules may still be overridden at runtime via CLI flags.
    """
    parser = argparse.ArgumentParser(
        description=f"CAMA + sale history scraper for county {county_fips}."
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
        "--delay", type=float, default=default_delay,
        help=f"Lower bound of per-request delay in seconds (default: {default_delay})",
    )
    parser.add_argument(
        "--delay-max", type=float, default=default_delay_max,
        help=f"Upper bound of per-request delay in seconds (default: {default_delay_max})",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-fetch parcels that already have cama_enriched_at set",
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
        county_fips=county_fips,
        source_name=source_name,
        fetch_page_fn=fetch_page_fn,
        parse_building_fn=parse_building_fn,
        parse_sales_fn=parse_sales_fn,
        headers=headers,
        target_dor_ucs=target_dor_ucs,
        limit=args.limit,
        parcel=args.parcel,
        dry_run=args.dry_run,
        delay=args.delay,
        delay_max=args.delay_max,
        force=args.force,
        rest_every=rest_every,
        rest_seconds=rest_seconds,
    ))
