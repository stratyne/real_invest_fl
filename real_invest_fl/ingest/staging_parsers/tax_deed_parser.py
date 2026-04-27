"""
real_invest_fl/ingest/staging_parsers/tax_deed_parser.py
----------------------------------------------------------
Parses manually created CSV files of active tax deed auction listings
from escambia.realtaxdeed.com.

Input:
    CSV files dropped into data/staging/tax_deed/
    Source: https://escambia.realtaxdeed.com (manual retrieval)
    Recommended cycle: Monthly (one auction day per month)

Expected CSV columns:
    case_number, certificate_number, parcel_id, property_address,
    city, zipcode, auction_date, opening_bid, assessed_value, listing_url

Parcel matching:
    Direct parcel_id lookup — portal displays Parcel ID on each card.

Deduplication:
    case_number is the unique key.

ETHICAL / LEGAL NOTICE:
    Source data is retrieved manually from the Escambia County Clerk's
    public tax deed auction portal under Florida Statutes Chapter 119.
    No automated scraping is performed.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import settings  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("tax_deed_parser")

COUNTY_FIPS = "12033"
STAGING_DIR = ROOT / "data" / "staging" / "tax_deed"
SIGNAL_TIER = 1
SIGNAL_TYPE = "tax_deed"
SOURCE_NAME = "escambia_realtaxdeed"

TEMPLATE_HEADER = (
    "case_number,certificate_number,parcel_id,property_address,"
    "city,zipcode,auction_date,opening_bid,assessed_value,listing_url\n"
)


def _write_template_if_missing() -> None:
    template_path = STAGING_DIR / "tax_deed_template.csv"
    if not template_path.exists():
        template_path.write_text(TEMPLATE_HEADER)
        logger.info("Template written to %s", template_path)


def _get_existing_cases(engine) -> set[str]:
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT DISTINCT raw_listing_json->>'case_number' AS cn
            FROM listing_events
            WHERE source = :source
            AND raw_listing_json->>'case_number' IS NOT NULL
        """), {"source": SOURCE_NAME})
        return {row.cn for row in result.fetchall() if row.cn}


def _get_filter_profile_id(engine) -> int | None:
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT id FROM filter_profiles
            WHERE county_fips = :fips AND is_active = true LIMIT 1
        """), {"fips": COUNTY_FIPS})
        row = result.fetchone()
        return row.id if row else None


def _lookup_parcel(parcel_id_raw: str, engine) -> dict | None:
    from real_invest_fl.utils.parcel_id import normalize_parcel_id
    for pid in [normalize_parcel_id(parcel_id_raw.strip(), COUNTY_FIPS),
                parcel_id_raw.strip()]:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT parcel_id, county_fips, jv, arv_estimate, tot_lvg_area,
                       phy_addr1, phy_zipcd
                FROM properties
                WHERE parcel_id = :pid
                AND county_fips = :fips
                AND mqi_qualified = true
            """), {"pid": pid, "fips": COUNTY_FIPS})
            row = result.fetchone()
            if row:
                return dict(row._mapping)
    return None


def parse_tax_deed_file(filepath: Path, engine, dry_run: bool) -> dict:
    logger.info("Parsing file: %s", filepath.name)

    if "template" in filepath.name.lower():
        return {"read": 0, "matched": 0, "inserted": 0,
                "skipped_duplicate": 0, "unmatched": 0}

    try:
        df = pd.read_csv(filepath, dtype=str)
    except Exception as exc:
        logger.error("Failed to read CSV %s: %s", filepath, exc)
        return {"error": str(exc)}

    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    required = {"case_number", "parcel_id"}
    missing  = required - set(df.columns)
    if missing:
        logger.error("Missing required columns %s in %s", missing, filepath.name)
        return {"error": f"missing columns: {missing}"}

    existing_cases    = _get_existing_cases(engine)
    filter_profile_id = _get_filter_profile_id(engine)

    stats = {
        "read": 0, "matched": 0, "inserted": 0,
        "skipped_duplicate": 0, "unmatched": 0,
    }

    insert_sql = text("""
        INSERT INTO listing_events (
            county_fips, parcel_id, signal_tier, signal_type,
            list_price, list_date, source, listing_url,
            arv_estimate, arv_source, arv_spread,
            filter_profile_id, workflow_status,
            raw_listing_json, scraped_at, created_at, updated_at
        ) VALUES (
            :county_fips, :parcel_id, :signal_tier, :signal_type,
            :list_price, :list_date, :source, :listing_url,
            :arv_estimate, :arv_source, :arv_spread,
            :filter_profile_id, :workflow_status,
            :raw_listing_json, :scraped_at, NOW(), NOW()
        )
    """)

    for _, row in df.iterrows():
        stats["read"] += 1
        case_number = str(row.get("case_number", "") or "").strip()
        if not case_number or case_number in existing_cases:
            if case_number in existing_cases:
                stats["skipped_duplicate"] += 1
            continue

        parcel_id_raw = str(row.get("parcel_id", "") or "").strip()
        if not parcel_id_raw:
            stats["unmatched"] += 1
            continue

        parcel = _lookup_parcel(parcel_id_raw, engine)
        if parcel is None:
            stats["unmatched"] += 1
            logger.info(
                "Parcel not in MQI | case=%s parcel_id=%s",
                case_number, parcel_id_raw,
            )
            continue

        stats["matched"] += 1

        list_price: int | None = None
        bid_raw = str(row.get("opening_bid", "") or "").replace("$", "").replace(",", "").strip()
        try:
            list_price = int(float(bid_raw)) if bid_raw else None
        except ValueError:
            pass

        list_date: date | None = None
        try:
            date_raw = str(row.get("auction_date", "") or "").strip()
            list_date = pd.to_datetime(date_raw).date() if date_raw else None
        except Exception:
            pass

        arv_estimate = parcel.get("arv_estimate")
        arv_spread: int | None = None
        if arv_estimate and list_price and list_price > 0:
            arv_spread = arv_estimate - list_price

        raw_json = {
            "case_number":       case_number,
            "certificate_number": str(row.get("certificate_number", "") or "").strip(),
            "parcel_id_raw":     parcel_id_raw,
            "assessed_value":    str(row.get("assessed_value", "") or "").strip(),
            "source_file":       filepath.name,
        }

        payload = {
            "county_fips":       parcel["county_fips"],
            "parcel_id":         parcel["parcel_id"],
            "signal_tier":       SIGNAL_TIER,
            "signal_type":       SIGNAL_TYPE,
            "list_price":        list_price,
            "list_date":         list_date,
            "source":            SOURCE_NAME,
            "listing_url":       str(row.get("listing_url", "") or "").strip() or None,
            "arv_estimate":      arv_estimate,
            "arv_source":        "JV",
            "arv_spread":        arv_spread,
            "filter_profile_id": filter_profile_id,
            "workflow_status":   "NEW",
            "raw_listing_json":  json.dumps(raw_json),
            "scraped_at":        datetime.now(tz=timezone.utc),
        }

        if dry_run:
            logger.info(
                "[DRY-RUN] Would insert | case=%s parcel=%s "
                "list_price=%s arv_spread=%s",
                case_number, parcel["parcel_id"], list_price, arv_spread,
            )
            stats["inserted"] += 1
            continue

        try:
            with engine.begin() as conn:
                conn.execute(insert_sql, payload)
            existing_cases.add(case_number)
            stats["inserted"] += 1
        except Exception as exc:
            logger.error("Insert failed for case=%s: %s", case_number, exc)

    return stats


def run_tax_deed_import(dry_run: bool, specific_file: Path | None) -> None:
    t_start = time.time()
    engine = create_engine(settings.sync_database_url, echo=False)
    _write_template_if_missing()

    files = [specific_file] if specific_file else sorted(STAGING_DIR.glob("*.csv"))
    if not files:
        logger.info("No CSV files in %s — nothing to process.", STAGING_DIR)
        return

    logger.info("Found %d file(s) to process", len(files))
    for filepath in files:
        stats = parse_tax_deed_file(filepath, engine, dry_run)
        logger.info(
            "File complete | read=%d matched=%d inserted=%d "
            "skipped=%d unmatched=%d | %s",
            stats.get("read", 0), stats.get("matched", 0),
            stats.get("inserted", 0), stats.get("skipped_duplicate", 0),
            stats.get("unmatched", 0), filepath.name,
        )

    logger.info("Tax deed import complete | duration=%.1fs", time.time() - t_start)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse tax deed CSVs into listing_events."
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--file", type=Path, default=None)
    args = parser.parse_args()
    run_tax_deed_import(dry_run=args.dry_run, specific_file=args.file)


if __name__ == "__main__":
    main()
