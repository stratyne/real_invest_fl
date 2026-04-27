"""
Tax Deed Staging Parser — Project Penstock
==========================================
Parses raw two-column key-value CSV files pasted directly from
escambia.realtaxdeed.com into data/staging/tax_deed/.

File format (no header row):
  Column A (key), Column B (value)
  Records are separated by a row where column A begins with
  "Auction Starts" (leading whitespace/garbage chars are stripped).

Usage:
    python scripts/run_staging_import.py --source tax_deed [--dry-run]

Ethical notice:
    This parser reads manually saved files. No automated scraping of
    escambia.realtaxdeed.com is performed (robots.txt: Disallow /).
    Data is public record under Florida Statute § 119.07.
"""

from __future__ import annotations

import csv
import logging
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent.parent.parent
STAGING_DIR = ROOT / "data" / "staging" / "tax_deed"
COUNTY_FIPS = "12033"
SOURCE_NAME = "escambia_realtaxdeed"
SIGNAL_TIER = 1
SIGNAL_TYPE = "tax_deed"

log = logging.getLogger("tax_deed_parser")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean(value: str) -> str:
    """Strip leading/trailing whitespace and non-printable characters."""
    value = unicodedata.normalize("NFKC", value)
    return value.strip()


def _is_block_separator(key: str) -> bool:
    """Return True if this row marks the start of a new auction record."""
    return re.sub(r"[^\w]", "", key).lower().startswith("auctionstarts")


def _parse_money(value: str) -> Optional[int]:
    """Convert '$14,684.89' -> 14684 (integer dollars, truncated)."""
    digits = re.sub(r"[^\d.]", "", value)
    try:
        return int(float(digits))
    except (ValueError, TypeError):
        return None


def _parse_auction_dt(value: str) -> Optional[date]:
    """Parse '05/06/2026 10:00 AM CT' -> date(2026, 5, 6)."""
    m = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", value)
    if m:
        try:
            return datetime.strptime(m.group(1), "%m/%d/%Y").date()
        except ValueError:
            pass
    return None


# ---------------------------------------------------------------------------
# Block splitting
# ---------------------------------------------------------------------------

def _split_into_blocks(rows: list[list[str]]) -> list[list[list[str]]]:
    """
    Split the full CSV row list into individual auction record blocks.
    Each block begins at an 'Auction Starts' row.
    The very first block (before any separator) is discarded if empty.
    """
    blocks: list[list[list[str]]] = []
    current: list[list[str]] = []
    for row in rows:
        if len(row) < 1:
            continue
        key = _clean(row[0])
        if _is_block_separator(key):
            if current:
                blocks.append(current)
            current = [row]
        else:
            current.append(row)
    if current:
        blocks.append(current)
    return blocks


# ---------------------------------------------------------------------------
# Record extraction
# ---------------------------------------------------------------------------

def _extract_record(block: list[list[str]]) -> Optional[dict]:
    log.debug("  Block keys: %s", [row[0] if row else '' for row in block])
    """
    Parse one auction block (list of [key, value] rows) into a dict.
    Returns None if required fields are missing.
    """
    kv: dict[str, str] = {}
    address_lines: list[str] = []

    for row in block:
        if len(row) < 2:
            # Might be a bare label row (e.g. 'TAXDEED' with no value)
            if len(row) == 1:
                val = _clean(row[0])
                if val:
                    kv["_type_marker"] = val
            continue
        key = _clean(row[0])
        val = _clean(row[1])

        if _is_block_separator(key):
            kv["auction_dt_raw"] = val if val else key
            continue

        key_lower = key.lower().rstrip(":").strip().replace(" ", "_").replace("#", "num")
        if key_lower in ("case_num", "case_#"):
            kv["case_number"] = val
        elif key_lower == "certificate_num":
            kv["certificate_number"] = val
        elif key_lower == "opening_bid":
            kv["opening_bid_raw"] = val
        elif key_lower == "parcel_id":
            kv["parcel_id_raw"] = val
        elif key_lower == "assessed_value":
            kv["assessed_value_raw"] = val
        elif key_lower in ("address", "property_address"):
            # First address row = street, second = city/state/ZIP
            address_lines.append(val)
        elif not key and val:
            # Continuation row — likely second address line
            address_lines.append(val)
        elif key_lower == "auction_starts":
            kv["auction_dt_raw"] = val

    # Reconstruct address
    kv["address_street"] = address_lines[0] if len(address_lines) > 0 else None
    kv["address_csz"] = address_lines[1] if len(address_lines) > 1 else None

    # Validate required fields
    if not kv.get("parcel_id_raw") or not kv.get("case_number"):
        return None

    return kv


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _get_filter_profile_id(conn) -> Optional[int]:
    row = conn.execute(
        text(
            "SELECT id FROM filter_profiles "
            "WHERE county_fips = :fips AND is_active = true LIMIT 1"
        ),
        {"fips": COUNTY_FIPS},
    ).fetchone()
    return row[0] if row else None


def _get_existing_case_numbers(conn) -> set[str]:
    rows = conn.execute(
        text(
            "SELECT mls_number FROM listing_events "
            "WHERE source = :src AND mls_number IS NOT NULL"
        ),
        {"src": SOURCE_NAME},
    ).fetchall()
    return {r[0] for r in rows}


def _lookup_parcel(conn, raw_parcel_id: str) -> Optional[str]:
    """Normalize parcel ID and confirm it exists in properties."""
    # Escambia parcel IDs from the portal may have dashes or spaces; strip them.
    normalized = re.sub(r"[^A-Z0-9]", "", raw_parcel_id.upper())
    row = conn.execute(
        text(
            "SELECT parcel_id FROM properties "
            "WHERE parcel_id = :pid AND county_fips = :fips LIMIT 1"
        ),
        {"pid": normalized, "fips": COUNTY_FIPS},
    ).fetchone()
    return row[0] if row else None


def _extract_zip(csz: Optional[str]) -> Optional[str]:
    """Extract 5-digit ZIP from 'PENSACOLA, FL 32505'."""
    if not csz:
        return None
    m = re.search(r"\b(\d{5})\b", csz)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_tax_deed_import(
    dry_run: bool = False,
    specific_file: Optional[Path] = None,
) -> dict:
    """
    Parse all .csv files in data/staging/tax_deed/ and insert
    tax deed auction records into listing_events.

    Returns a summary dict with read/matched/inserted/skipped/unmatched counts.
    """
    from config.settings import settings
    engine = create_engine(settings.sync_database_url)
    files = (
        [specific_file]
        if specific_file
        else sorted(STAGING_DIR.glob("*.csv"))
    )

    if not files:
        log.warning("No .csv files found in %s", STAGING_DIR)
        return {"read": 0, "matched": 0, "inserted": 0, "skipped": 0, "unmatched": 0}

    totals = {"read": 0, "matched": 0, "inserted": 0, "skipped": 0, "unmatched": 0}

    for filepath in files:
        log.info("Processing file: %s", filepath.name)
        with open(filepath, newline="", encoding="latin-1") as fh:
            rows = list(csv.reader(fh))

        blocks = _split_into_blocks(rows)
        log.info("  Found %d auction blocks", len(blocks))

        with engine.begin() as conn:
            existing_cases = _get_existing_case_numbers(conn)
            filter_profile_id = _get_filter_profile_id(conn)

            for block in blocks:
                totals["read"] += 1
                record = _extract_record(block)

                if record is None:
                    log.debug("  Skipping unparseable block")
                    totals["unmatched"] += 1
                    continue

                case_number = record.get("case_number", "")
                if case_number in existing_cases:
                    log.debug("  Duplicate case %s — skipping", case_number)
                    totals["skipped"] += 1
                    continue

                parcel_id = _lookup_parcel(conn, record["parcel_id_raw"])
                if parcel_id is None:
                    log.debug(
                        "  Case %s — parcel %s not in MQI — skipping",
                        case_number,
                        record["parcel_id_raw"],
                    )
                    totals["unmatched"] += 1
                    continue

                totals["matched"] += 1

                opening_bid = _parse_money(record.get("opening_bid_raw", ""))
                assessed_value = _parse_money(record.get("assessed_value_raw", ""))
                auction_date = _parse_auction_dt(record.get("auction_dt_raw", ""))
                zip_code = _extract_zip(record.get("address_csz"))

                street = record.get("address_street") or ""
                csz = record.get("address_csz") or ""
                full_address = f"{street}, {csz}".strip(", ")

                now = datetime.utcnow()

                if dry_run:
                    log.info(
                        "  [DRY-RUN] Would insert | case=%s | parcel=%s | "
                        "bid=$%s | date=%s",
                        case_number,
                        parcel_id,
                        opening_bid,
                        auction_date,
                    )
                    totals["inserted"] += 1
                    continue

                conn.execute(
                    text(
                        """
                        INSERT INTO listing_events (
                            county_fips, parcel_id, listing_type, list_price,
                            list_date, source, listing_url,
                            mls_number,
                            signal_tier, signal_type,
                            workflow_status, notes,
                            raw_listing_json, scraped_at, created_at, updated_at,
                            filter_profile_id
                        ) VALUES (
                            :county_fips, :parcel_id, :listing_type, :list_price,
                            :list_date, :source, :listing_url,
                            :mls_number,
                            :signal_tier, :signal_type,
                            :workflow_status, :notes,
                            CAST(:raw_listing_json AS jsonb), :scraped_at, :created_at, :updated_at,
                            :filter_profile_id
                        )
                        """
                    ),
                    {
                        "county_fips": COUNTY_FIPS,
                        "parcel_id": parcel_id,
                        "listing_type": "tax_deed_auction",
                        "list_price": opening_bid,
                        "list_date": auction_date,
                        "source": SOURCE_NAME,
                        "listing_url": "https://escambia.realtaxdeed.com/",
                        "mls_number": case_number,
                        "signal_tier": SIGNAL_TIER,
                        "signal_type": SIGNAL_TYPE,
                        "workflow_status": "new",
                        "notes": (
                            f"Certificate: {record.get('certificate_number', 'N/A')} | "
                            f"Assessed: ${assessed_value or 'N/A'} | "
                            f"Address: {full_address}"
                        ),
                        "raw_listing_json": (
                            f'{{"case_number": "{case_number}", '
                            f'"certificate_number": "{record.get("certificate_number", "")}", '
                            f'"opening_bid": {opening_bid or "null"}, '
                            f'"assessed_value": {assessed_value or "null"}, '
                            f'"address": "{full_address}", '
                            f'"zip": "{zip_code or ""}"}}'
                        ),
                        "scraped_at": now,
                        "created_at": now,
                        "updated_at": now,
                        "filter_profile_id": filter_profile_id,
                    },
                )
                existing_cases.add(case_number)
                totals["inserted"] += 1

    log.info(
        "Tax deed import complete | read=%d matched=%d inserted=%d "
        "skipped=%d unmatched=%d",
        totals["read"],
        totals["matched"],
        totals["inserted"],
        totals["skipped"],
        totals["unmatched"],
    )
    return totals
