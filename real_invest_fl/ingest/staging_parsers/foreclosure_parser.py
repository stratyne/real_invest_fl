"""
Foreclosure Staging Parser — Project Penstock
=============================================
Parses raw two-column key-value CSV files pasted directly from
escambia.realforeclose.com into data/staging/foreclosure/.

File format (no header row):
  Column A (key), Column B (value)
  Records separated by a row where column A begins with
  "Auction Starts" (leading whitespace/garbage chars are stripped).
  Single-listing days may have a leading garbage character before 'Auction'.

Usage:
    python scripts/run_staging_import.py --source foreclosure [--dry-run]

Ethical notice:
    This parser reads manually saved files. No automated scraping of
    escambia.realforeclose.com is performed (robots.txt: Disallow /).
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
STAGING_DIR = ROOT / "data" / "staging" / "foreclosure"
COUNTY_FIPS = "12033"
SOURCE_NAME = "escambia_realforeclose"
SIGNAL_TIER = 1
SIGNAL_TYPE = "foreclosure_sale"

log = logging.getLogger("foreclosure_parser")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean(value: str) -> str:
    """Strip whitespace, non-printable, and non-ASCII garbage characters."""
    value = unicodedata.normalize("NFKC", value)
    return value.strip()


def _is_block_separator(key: str) -> bool:
    """
    Return True if this row marks the start of a new auction record.
    Handles leading garbage char (e.g., '\x00Auction Starts').
    """
    stripped = re.sub(r"[^\w]", "", key).lower()
    return stripped.startswith("auctionstarts")


def _parse_money(value: str) -> Optional[int]:
    """Convert '$264,456.66' -> 264456 (integer dollars, truncated)."""
    digits = re.sub(r"[^\d.]", "", value)
    try:
        return int(float(digits))
    except (ValueError, TypeError):
        return None


def _parse_auction_dt(value: str) -> Optional[date]:
    """Parse '05/01/2026 11:00 AM CT' -> date(2026, 5, 1)."""
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
    Each block begins at an 'Auction Starts' separator row.
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
    Parse one auction block into a dict.
    Returns None if required fields (parcel_id, case_number) are missing.
    """
    kv: dict[str, str] = {}
    address_lines: list[str] = []

    for row in block:
        if len(row) < 2:
            if len(row) == 1:
                val = _clean(row[0])
                if val:
                    kv["_type_marker"] = val
            continue

        key = _clean(row[0])
        val = _clean(row[1])

        if _is_block_separator(key):
            # The value cell contains date/time, but sometimes it is
            # in the key cell itself when the paste has only one column.
            kv["auction_dt_raw"] = val if val else key
            continue

        key_norm = key.lower().rstrip(":").strip().replace(" ", "_").replace("#", "num")

        if key_norm in ("case_num", "case_#", "case_number"):
            kv["case_number"] = val
        elif key_norm == "final_judgment_amount":
            kv["final_judgment_raw"] = val
        elif key_norm == "parcel_id":
            kv["parcel_id_raw"] = val
        elif key_norm == "assessed_value":
            kv["assessed_value_raw"] = val
        elif key_norm == "plaintiff_max_bid":
            kv["plaintiff_max_bid_raw"] = val
        elif key_norm in ("address", "property_address"):
            address_lines.append(val)
        elif not key and val:
            # Continuation row — likely city/state/ZIP line of the address
            address_lines.append(val)
        elif key_norm == "auction_starts":
            kv["auction_dt_raw"] = val

    kv["address_street"] = address_lines[0] if len(address_lines) > 0 else None
    kv["address_csz"] = address_lines[1] if len(address_lines) > 1 else None

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
    """Normalize parcel ID and verify it exists in properties."""
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
    if not csz:
        return None
    m = re.search(r"\b(\d{5})\b", csz)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_foreclosure_import(
    dry_run: bool = False,
    specific_file: Optional[Path] = None,
) -> dict:
    """
    Parse all .csv files in data/staging/foreclosure/ and insert
    foreclosure auction records into listing_events.

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

                final_judgment = _parse_money(record.get("final_judgment_raw", ""))
                plaintiff_max_bid = _parse_money(record.get("plaintiff_max_bid_raw", ""))
                assessed_value = _parse_money(record.get("assessed_value_raw", ""))
                auction_date = _parse_auction_dt(record.get("auction_dt_raw", ""))
                zip_code = _extract_zip(record.get("address_csz"))

                # Use plaintiff max bid as list price if final judgment not available
                list_price = final_judgment or plaintiff_max_bid

                street = record.get("address_street") or ""
                csz = record.get("address_csz") or ""
                full_address = f"{street}, {csz}".strip(", ")

                now = datetime.utcnow()

                if dry_run:
                    log.info(
                        "  [DRY-RUN] Would insert | case=%s | parcel=%s | "
                        "judgment=$%s | date=%s",
                        case_number,
                        parcel_id,
                        final_judgment,
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
                        "listing_type": "foreclosure_auction",
                        "list_price": list_price,
                        "list_date": auction_date,
                        "source": SOURCE_NAME,
                        "listing_url": "https://escambia.realforeclose.com/",
                        "mls_number": case_number,
                        "signal_tier": SIGNAL_TIER,
                        "signal_type": SIGNAL_TYPE,
                        "workflow_status": "new",
                        "notes": (
                            f"Final judgment: ${final_judgment or 'N/A'} | "
                            f"Plaintiff max bid: ${plaintiff_max_bid or 'N/A'} | "
                            f"Assessed: ${assessed_value or 'N/A'} | "
                            f"Address: {full_address}"
                        ),
                        "raw_listing_json": (
                            f'{{"case_number": "{case_number}", '
                            f'"final_judgment": {final_judgment or "null"}, '
                            f'"plaintiff_max_bid": {plaintiff_max_bid or "null"}, '
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
        "Foreclosure import complete | read=%d matched=%d inserted=%d "
        "skipped=%d unmatched=%d",
        totals["read"],
        totals["matched"],
        totals["inserted"],
        totals["skipped"],
        totals["unmatched"],
    )
    return totals
