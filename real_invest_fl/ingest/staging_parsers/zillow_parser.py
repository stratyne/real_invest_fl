"""
real_invest_fl/ingest/staging_parsers/zillow_parser.py
-------------------------------------------------------------------
Parses manually copied Zillow foreclosure listing data and writes
matching records to listing_events.

Input:
    CSV files dropped into data/staging/zillow/
    Created by: copy/paste from Zillow foreclosure search results
    into a spreadsheet with comma-separation disabled, saved as .csv
    Recommended cycle: Weekly — copy current results, drop file, run parser

File format (one value per line, no header):
    $NNN,NNN.NN          <- price line — marks start of new listing block
    N bdsN baN,NNN sqftForeclosure  <- specs line
    Street, City, FL ZIP <- address line (first occurrence)
    BROKERAGE NAME       <- agent/brokerage line
    More                 <- discard
    [optional desc line] <- discard
    Save                 <- discard
                         <- blank line — discard
    Previous photoNext photo  <- discard
    Street, City, FL ZIP <- address repeated — discard
    [next listing starts with $ price line]

Parcel matching strategy:
    Normalize address from listing, match against phy_addr1 + phy_zipcd
    in properties table. Exact normalized match only at this stage.

Deduplication:
    address + list_price is the unique key.
    Same address, same price = skip (true duplicate).
    Same address, new price = insert new row (price reduction event).

Bed/bath enrichment:
    If matched parcel has NULL bedrooms/bathrooms in properties,
    update properties with values parsed from the listing.
    bed_bath_source = 'zillow_foreclosure'

Usage:
    python scripts/run_staging_import.py --source zillow [--dry-run]
    python -m real_invest_fl.ingest.staging_parsers.zillow_parser
    python -m real_invest_fl.ingest.staging_parsers.zillow_parser --dry-run
    python -m real_invest_fl.ingest.staging_parsers.zillow_parser --file path/to/file.csv

ETHICAL / LEGAL NOTICE:
    Source data is copied manually from Zillow's public search results.
    No automated scraping is performed against Zillow's servers.
    Data is used solely for private investment research.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, text

# ── path bootstrap ─────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import settings  # noqa: E402
from real_invest_fl.utils.text import normalize_street_address  # noqa: E402
from real_invest_fl.ingest.listing_matcher import (  # noqa: E402
    lookup_parcel_by_address,
    enrich_bed_bath,
)

# ── logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("zillow_parser")

# ── constants ──────────────────────────────────────────────────────────────
COUNTY_FIPS  = "12033"
STAGING_DIR  = ROOT / "data" / "staging" / "zillow"
SIGNAL_TIER  = 3
SIGNAL_TYPE  = "foreclosure"
LISTING_TYPE = "foreclosure"
SOURCE_NAME  = "zillow_foreclosure"

# Lines that are always structural noise — discard unconditionally
_NOISE_PATTERNS = re.compile(
    r"^(More|Save|Previous photoNext photo|Save this search.*|"
    r".*to get email alerts.*)$",
    re.IGNORECASE,
)


# ── text normalization ─────────────────────────────────────────────────────

def _strip_quotes(line: str) -> str:
    """Remove surrounding double-quotes inserted by CSV wrapping."""
    line = line.strip()
    if line.startswith('"') and line.endswith('"'):
        line = line[1:-1]
    return line.strip()


def _is_price_line(line: str) -> bool:
    """Return True if line is a price — marks start of a new listing block."""
    return bool(re.match(r"^\$[\d,]+(\.\d{2})?$", line))


def _parse_price(line: str) -> Optional[int]:
    """'$224,900.00' -> 224900"""
    digits = re.sub(r"[^\d]", "", line)
    try:
        return int(digits) // 100 if "." in line else int(digits)
    except (ValueError, TypeError):
        return None


def _parse_specs(line: str) -> dict:
    """
    Parse '3 bds2 ba1,319 sqftForeclosure' into components.
    Returns dict with keys: bedrooms, bathrooms, sqft, listing_type.
    All values are None if line does not match expected format.
    """
    result = {
        "bedrooms":    None,
        "bathrooms":   None,
        "sqft":        None,
        "listing_type": None,
    }

    # Bedrooms
    bd_match = re.search(r"(\d+)\s*bds?", line, re.IGNORECASE)
    if bd_match:
        result["bedrooms"] = int(bd_match.group(1))

    # Bathrooms — handle half baths e.g. "1.5 ba"
    ba_match = re.search(r"([\d.]+)\s*ba", line, re.IGNORECASE)
    if ba_match:
        try:
            result["bathrooms"] = float(ba_match.group(1))
        except ValueError:
            pass

    # Sqft — digits with optional comma before "sqft"
    sqft_match = re.search(r"([\d,]+)\s*sqft", line, re.IGNORECASE)
    if sqft_match:
        result["sqft"] = int(sqft_match.group(1).replace(",", ""))

    # Listing type — word(s) after sqft
    type_match = re.search(r"sqft\s*([A-Za-z\s\-]+)$", line, re.IGNORECASE)
    if type_match:
        result["listing_type"] = type_match.group(1).strip()

    return result


def _is_address_line(line: str) -> bool:
    """
    Return True if line looks like a property address.
    Pattern: anything ending in FL NNNNN
    """
    return bool(re.search(r",\s*FL\s+\d{5}$", line, re.IGNORECASE))


def _normalize_address(address: str) -> str:
    """Delegate to the shared street address normalizer in utils/text.py."""
    return normalize_street_address(address)


def _extract_zip(address: str) -> Optional[str]:
    """Extract 5-digit ZIP from end of address string."""
    m = re.search(r"\b(\d{5})\s*$", address)
    return m.group(1) if m else None


def _extract_street(address: str) -> str:
    """
    Extract the street portion only (before first comma) for parcel matching.

    Output is passed to lookup_parcel_by_address() in listing_matcher.py,
    which owns canonical normalization (suffix abbreviation, directional
    contraction, digit-letter injection, unit stripping) and the full
    three-level address fallback.

    Unit designators are preserved in the output so that
    lookup_parcel_by_address() can perform Level 2 unit normalization
    on the strip_unit=False form internally.

    Does NOT strip units or apply digit-letter injection here —
    those steps are delegated to lookup_parcel_by_address().
    """
    import re
    from real_invest_fl.utils.text import (
        _SUFFIX_RE, _STREET_SUFFIX_MAP,
        _DIRECTIONAL_MAP, _DIRECTIONAL_FULL_WORDS,
    )
    parts = address.split(",")
    street = parts[0].strip().upper() if parts else address.upper()
    # Collapse whitespace
    street = re.sub(r"\s+", " ", street.strip())
    # Suffix abbreviation
    street = _SUFFIX_RE.sub(lambda m: _STREET_SUFFIX_MAP[m.group(1)], street)
    street = re.sub(r"\s+", " ", street.strip())
    # Directional contraction
    for full, abbr in _DIRECTIONAL_MAP.items():
        not_another_dir = "(?!" + "|".join(
            re.escape(d) + r"\b" for d in _DIRECTIONAL_FULL_WORDS
        ) + ")"
        pattern = re.compile(
            r"^(\d+\s+)" + re.escape(full) + r"\s+" + not_another_dir
        )
        street = pattern.sub(r"\1" + abbr + " ", street)
    return re.sub(r"\s+", " ", street.strip())


# ── block splitting ────────────────────────────────────────────────────────

def _split_into_blocks(lines: list[str]) -> list[list[str]]:
    """
    Split cleaned line list into listing blocks.
    Each block begins at a price line.
    Lines before the first price line are discarded.
    """
    blocks: list[list[str]] = []
    current: list[str] = []

    for line in lines:
        if _is_price_line(line):
            if current:
                blocks.append(current)
            current = [line]
        else:
            if current:  # Only accumulate once we've seen a price line
                current.append(line)

    if current:
        blocks.append(current)

    return blocks


# ── record extraction ──────────────────────────────────────────────────────

def _extract_record(block: list[str]) -> Optional[dict]:
    """
    Extract a listing record from a single block of lines.

    Block structure (lines already cleaned, noise removed):
        line 0: price          e.g. '$224,900.00'
        line 1: specs          e.g. '3 bds2 ba1,319 sqftForeclosure'
        line 2: address        e.g. '4831 Olive Rd #4A, Pensacola, FL 32514'
        line 3: brokerage      e.g. 'ASSIST 2 SELL REAL ESTATE'
        line 4+: address repeat and any remaining noise (already filtered)

    Returns None if required fields cannot be parsed, with [REVIEW] output.
    """
    if not block:
        return None

    price_line = block[0]
    list_price = _parse_price(price_line)

    if list_price is None:
        print(f"[REVIEW] Cannot parse price from block starting: {price_line!r}")
        return None

    # Find specs line — first non-price line containing 'bds' or 'ba'
    specs = None
    specs_idx = None
    for i, line in enumerate(block[1:], start=1):
        if re.search(r"\d+\s*bds?", line, re.IGNORECASE):
            specs = _parse_specs(line)
            specs_idx = i
            break

    if specs is None:
        print(f"[REVIEW] Cannot parse specs from block with price {price_line!r} — "
              f"block lines: {block}")
        return None

    # Find first address line after specs
    address = None
    address_idx = None
    for i, line in enumerate(block[specs_idx + 1:], start=specs_idx + 1):
        if _is_address_line(line):
            address = line
            address_idx = i
            break

    if address is None:
        print(f"[REVIEW] Cannot find address in block with price {price_line!r} — "
              f"block lines: {block}")
        return None

    # Brokerage — first non-empty, non-address, non-noise line after address
    brokerage = None
    if address_idx is not None:
        for line in block[address_idx + 1:]:
            if line and not _is_address_line(line):
                brokerage = line
                break

    return {
        "list_price":   list_price,
        "bedrooms":     specs["bedrooms"],
        "bathrooms":    specs["bathrooms"],
        "sqft":         specs["sqft"],
        "listing_type": specs["listing_type"] or LISTING_TYPE,
        "address":      address,
        "street":       _extract_street(address),
        "zip_code":     _extract_zip(address),
        "brokerage":    brokerage,
    }


# ── DB helpers ─────────────────────────────────────────────────────────────

def _get_filter_profile_id(conn) -> Optional[int]:
    row = conn.execute(
        text(
            "SELECT id FROM filter_profiles "
            "WHERE county_fips = :fips AND is_active = true LIMIT 1"
        ),
        {"fips": COUNTY_FIPS},
    ).fetchone()
    return row[0] if row else None


def _get_existing_keys(conn) -> set[tuple[str, int]]:
    """
    Load (normalized_address, list_price) pairs already in listing_events
    for this source. Used for address + price deduplication.
    """
    rows = conn.execute(
        text(
            "SELECT raw_listing_json->>'normalized_address' AS addr, "
            "list_price "
            "FROM listing_events "
            "WHERE source = :src "
            "AND raw_listing_json->>'normalized_address' IS NOT NULL"
        ),
        {"src": SOURCE_NAME},
    ).fetchall()
    return {(r[0], r[1]) for r in rows if r[0] and r[1] is not None}


# ── file parser ────────────────────────────────────────────────────────────

def parse_zillow_file(
    filepath: Path,
    engine,
    dry_run: bool,
) -> dict:
    """
    Parse a single Zillow foreclosure CSV file and write listing_events.
    Returns summary dict with counts.
    """
    logger.info("Parsing file: %s", filepath.name)

    # ── Read and clean lines ────────────────────────────────────────── #
    try:
        raw_lines = filepath.read_text(encoding="utf-8-sig").splitlines()
    except UnicodeDecodeError:
        raw_lines = filepath.read_text(encoding="latin-1").splitlines()

    # Strip quotes, discard blank lines and noise
    cleaned: list[str] = []
    for raw in raw_lines:
        line = _strip_quotes(raw)
        if not line:
            continue
        if _NOISE_PATTERNS.match(line):
            continue
        cleaned.append(line)

    # ── Split into blocks ───────────────────────────────────────────── #
    blocks = _split_into_blocks(cleaned)
    logger.info("Found %d listing blocks in file", len(blocks))

    if not blocks:
        logger.warning("No listing blocks found in %s", filepath.name)
        return {
            "read": 0, "matched": 0, "inserted": 0,
            "skipped": 0, "unmatched": 0, "enriched": 0,
        }

    stats = {
        "read": 0, "matched": 0, "inserted": 0,
        "skipped": 0, "unmatched": 0, "enriched": 0,
    }

    today = date.today()

    with engine.begin() as conn:
        existing_keys = _get_existing_keys(conn)
        filter_profile_id = _get_filter_profile_id(conn)

        for block in blocks:
            stats["read"] += 1
            record = _extract_record(block)

            if record is None:
                stats["unmatched"] += 1
                continue

            # ── Dedup check ───────────────────────────────────────── #
            norm_address = _normalize_address(record["address"])
            dedup_key = (norm_address, record["list_price"])

            if dedup_key in existing_keys:
                logger.debug(
                    "Duplicate address+price — skipping: %s @ $%s",
                    norm_address, record["list_price"],
                )
                stats["skipped"] += 1
                continue

            # ── Parcel match ──────────────────────────────────────── #
            # street_for_match: strip trailing whitespace defensively.
            # _extract_street() output is accepted by lookup_parcel_by_address()
            # which owns canonical normalization. _extract_street() is unchanged.
            street_for_match = record["street"].strip()
            parcel = lookup_parcel_by_address(
                conn, street_for_match, record["zip_code"]
            )

            if parcel is None:
                print(
                    f"[REVIEW] No parcel match for address: "
                    f"{record['address']!r} "
                    f"(street={record['street']!r}, zip={record['zip_code']!r})"
                )
                stats["unmatched"] += 1
                continue

            stats["matched"] += 1

            # ── Bed/bath enrichment ───────────────────────────────── #
            if parcel["bedrooms"] is None or parcel["bathrooms"] is None:
                enriched = enrich_bed_bath(
                    conn,
                    parcel["parcel_id"],
                    parcel["county_fips"],
                    record["bedrooms"],
                    record["bathrooms"],
                    SOURCE_NAME,
                    dry_run,
                )
                if enriched:
                    stats["enriched"] += 1

            # ── Build raw_listing_json ────────────────────────────── #
            raw_json = {
                "normalized_address": norm_address,
                "address":            record["address"],
                "list_price":         record["list_price"],
                "bedrooms":           record["bedrooms"],
                "bathrooms":          record["bathrooms"],
                "sqft":               record["sqft"],
                "brokerage":          record["brokerage"],
                "source_file":        filepath.name,
                "parsed_at":          datetime.now(tz=timezone.utc).isoformat(),
            }

            # ── Price per sqft ────────────────────────────────────── #
            price_per_sqft = None
            if record["sqft"] and record["sqft"] > 0:
                price_per_sqft = round(
                    record["list_price"] / record["sqft"], 2
                )

            if dry_run:
                logger.info(
                    "[DRY-RUN] Would insert | address=%s | price=$%s | "
                    "beds=%s baths=%s | parcel=%s",
                    norm_address,
                    record["list_price"],
                    record["bedrooms"],
                    record["bathrooms"],
                    parcel["parcel_id"],
                )
                stats["inserted"] += 1
                existing_keys.add(dedup_key)
                continue

            # ── Insert listing_event ──────────────────────────────── #
            conn.execute(
                text("""
                    INSERT INTO listing_events (
                        county_fips, parcel_id,
                        listing_type, list_price, list_date,
                        price_per_sqft,
                        arv_estimate, arv_source,
                        source, signal_tier, signal_type,
                        listing_agent_name,
                        workflow_status,
                        filter_profile_id,
                        raw_listing_json,
                        scraped_at, created_at, updated_at
                    ) VALUES (
                        :county_fips, :parcel_id,
                        :listing_type, :list_price, :list_date,
                        :price_per_sqft,
                        :arv_estimate, :arv_source,
                        :source, :signal_tier, :signal_type,
                        :listing_agent_name,
                        :workflow_status,
                        :filter_profile_id,
                        CAST(:raw_listing_json AS jsonb),
                        :scraped_at, NOW(), NOW()
                    )
                """),
                {
                    "county_fips":        parcel["county_fips"],
                    "parcel_id":          parcel["parcel_id"],
                    "listing_type":       record["listing_type"] or LISTING_TYPE,
                    "list_price":         record["list_price"],
                    "list_date":          today,
                    "price_per_sqft":     price_per_sqft,
                    "arv_estimate":       parcel["arv_estimate"],
                    "arv_source":         "JV",
                    "source":             SOURCE_NAME,
                    "signal_tier":        SIGNAL_TIER,
                    "signal_type":        record["listing_type"] or SIGNAL_TYPE,
                    "listing_agent_name": record["brokerage"],
                    "workflow_status":    "new",
                    "filter_profile_id":  filter_profile_id,
                    "raw_listing_json":   json.dumps(raw_json),
                    "scraped_at":         datetime.now(tz=timezone.utc),
                },
            )

            existing_keys.add(dedup_key)
            stats["inserted"] += 1

    return stats


# ── directory runner ───────────────────────────────────────────────────────

def run_zillow_import(
    dry_run: bool = False,
    specific_file: Optional[Path] = None,
) -> dict:
    """
    Process all CSV files in data/staging/zillow/ or a single specified file.
    Returns aggregated summary dict.
    """
    t_start = time.time()
    engine = create_engine(settings.sync_database_url, echo=False)

    if specific_file:
        files = [specific_file]
    else:
        files = sorted(STAGING_DIR.glob("*.csv"))

    if not files:
        logger.info("No CSV files found in %s — nothing to process.", STAGING_DIR)
        return {
            "read": 0, "matched": 0, "inserted": 0,
            "skipped": 0, "unmatched": 0, "enriched": 0,
        }

    logger.info("Found %d file(s) to process", len(files))

    totals = {
        "read": 0, "matched": 0, "inserted": 0,
        "skipped": 0, "unmatched": 0, "enriched": 0,
    }

    for filepath in files:
        logger.info("--- Processing: %s ---", filepath.name)
        stats = parse_zillow_file(filepath, engine, dry_run)
        for key in totals:
            totals[key] += stats.get(key, 0)
        logger.info(
            "File complete | read=%d matched=%d inserted=%d "
            "skipped=%d unmatched=%d enriched=%d",
            stats.get("read", 0),
            stats.get("matched", 0),
            stats.get("inserted", 0),
            stats.get("skipped", 0),
            stats.get("unmatched", 0),
            stats.get("enriched", 0),
        )

    elapsed = time.time() - t_start
    logger.info(
        "Zillow import complete | "
        "read=%d matched=%d inserted=%d skipped=%d "
        "unmatched=%d enriched=%d duration=%.1fs",
        totals["read"], totals["matched"], totals["inserted"],
        totals["skipped"], totals["unmatched"], totals["enriched"],
        elapsed,
    )
    return totals


# ── CLI ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse Zillow foreclosure CSV exports into listing_events."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Parse and match but do not write to the database.",
    )
    parser.add_argument(
        "--file", type=Path, default=None,
        help="Process a single specific file instead of the staging directory.",
    )
    args = parser.parse_args()

    run_zillow_import(
        dry_run=args.dry_run,
        specific_file=args.file,
    )


if __name__ == "__main__":
    main()
