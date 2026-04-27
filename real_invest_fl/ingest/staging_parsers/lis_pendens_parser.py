"""
real_invest_fl/ingest/staging_parsers/lis_pendens_parser.py
-------------------------------------------------------------
Parses LandmarkWeb Excel exports of Lis Pendens filings and writes
matching records to listing_events.

Input:
    Excel files (.xlsx) dropped into data/staging/lis_pendens/
    Exported from: https://dory.escambiaclerk.com/LandmarkWeb
    Search parameters: Doc Type = LIS PENDENS, date range of your choice
    Recommended cycle: Weekly — export last 10 days, drop file, run parser

Columns expected (from LandmarkWeb export):
    Status, Direct Name, Reverse Name, Record Date, Doc Type,
    Book Type, Book, Page, CFN, DocLinks, Comments, Legal, DocLinks.1

Parcel matching strategy:
    Primary:   LOT + BLK + SUB from Legal field → fuzzy match against
               s_legal in properties table
    Secondary: SEC/TWP/RGE from Legal field → match against twn/rng/sec
               columns in properties table
    Fallback:  Log as unmatched — never insert without a parcel_id

Deduplication:
    CFN (Clerk File Number) is the unique key.
    Records already in listing_events with matching CFN in
    raw_listing_json are skipped.

Usage:
    python -m real_invest_fl.ingest.staging_parsers.lis_pendens_parser
    python -m real_invest_fl.ingest.staging_parsers.lis_pendens_parser --dry-run
    python -m real_invest_fl.ingest.staging_parsers.lis_pendens_parser --file path/to/file.xlsx

ETHICAL / LEGAL NOTICE:
    Source data is exported from the Escambia County Clerk's official
    public records portal under Florida Statutes Chapter 119.
    No automated scraping is performed. Data is retrieved manually
    and processed locally.
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

import pandas as pd
from sqlalchemy import create_engine, text

# ── path bootstrap ─────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import settings  # noqa: E402

# ── logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("lis_pendens_parser")

# ── constants ──────────────────────────────────────────────────────────────
COUNTY_FIPS     = "12033"
STAGING_DIR     = ROOT / "data" / "staging" / "lis_pendens"
SIGNAL_TIER     = 1
SIGNAL_TYPE     = "lis_pendens"
SOURCE_NAME     = "escambia_landmarkweb"
FUZZY_THRESHOLD = 72   # Lower than address matching — legal descriptions
                        # are abbreviated and inconsistent


# ── legal description parsing ──────────────────────────────────────────────

def _parse_legal(legal_raw: str) -> dict:
    """
    Parse the Legal field from LandmarkWeb into structured components.

    LandmarkWeb Legal field format (newline-separated):
        CN:2026 CA 000134           ← case number (always present)
        LOT:22 BLK:39 SUB:MONTCLAIR UN 7   ← subdivision record (sometimes)
        SEC:15 TWP:3N RGE:31W       ← section/township/range (sometimes)

    Returns dict with keys:
        case_number, lot, block, subdivision, sec, twp, rge, raw_legal
    """
    result = {
        "case_number":  None,
        "lot":          None,
        "block":        None,
        "subdivision":  None,
        "sec":          None,
        "twp":          None,
        "rge":          None,
        "raw_legal":    legal_raw or "",
    }

    if not legal_raw:
        return result

    # Normalize — replace newlines with spaces, collapse whitespace
    legal = re.sub(r"\s+", " ", str(legal_raw).replace("\n", " ")).strip()

    # Case number
    cn_match = re.search(r"CN:([\d\w\s]+CA[\s\d]+)", legal)
    if cn_match:
        result["case_number"] = cn_match.group(1).strip()

    # LOT / BLK / SUB
    lot_match = re.search(r"LOT:([\w\s/&,]+?)(?:\s+BLK:|$)", legal)
    blk_match = re.search(r"BLK:([\w\s/&,]+?)(?:\s+SUB:|$)", legal)
    sub_match = re.search(r"SUB:([\w\s/&,]+?)(?:\s+CN:|$)", legal)

    if lot_match:
        result["lot"] = lot_match.group(1).strip()
    if blk_match:
        result["block"] = blk_match.group(1).strip()
    if sub_match:
        result["subdivision"] = sub_match.group(1).strip()

    # SEC / TWP / RGE
    sec_match = re.search(r"SEC:([\w/]+)", legal)
    twp_match = re.search(r"TWP:([\w]+)", legal)
    rge_match = re.search(r"RGE:([\w]+)", legal)

    if sec_match:
        result["sec"] = sec_match.group(1).strip()
    if twp_match:
        result["twp"] = twp_match.group(1).strip()
    if rge_match:
        result["rge"] = rge_match.group(1).strip()

    return result


def _extract_owner_name(reverse_name_raw: str) -> str:
    """
    Extract the most likely individual owner name from the Reverse Name field.
    Multiple names are newline-separated. Institutional names are filtered.
    Returns the first non-institutional name, or the full raw string if none found.
    """
    if not reverse_name_raw:
        return ""

    institutional_keywords = {
        "BANK", "TRUST", "LLC", "INC", "CORP", "HOUSING",
        "URBAN", "DEVELOPMENT", "FINANCE", "FEDERAL", "COUNTY",
        "CITY", "STATE", "GOVERNMENT", "MANAGEMENT", "SOLUTIONS",
        "CAPITAL", "INVESTMENT", "MORTGAGE", "CREDIT", "UNION",
        "INTERNAL", "REVENUE", "SERVICE", "DEPARTMENT",
    }

    names = [n.strip() for n in str(reverse_name_raw).split("\n") if n.strip()]
    for name in names:
        words = set(name.upper().split())
        if not words.intersection(institutional_keywords):
            return name

    # All names appear institutional — return first one
    return names[0] if names else ""


# ── parcel matching ────────────────────────────────────────────────────────

def _build_legal_index(engine) -> tuple[dict, dict]:
    """
    Build two in-memory indexes from the properties table for parcel matching.

    Index 1 — s_legal index:
        Key:   normalized s_legal string
        Value: dict(parcel_id, county_fips, jv, arv_estimate, tot_lvg_area,
                    phy_addr1, phy_zipcd)

    Index 2 — sec/twn/rng index:
        Key:   "SEC|TWN|RNG" normalized string
        Value: list of parcel dicts (multiple parcels per section is common)

    Returns (legal_index, str_index)
    """
    logger.info("Building parcel indexes from properties table...")

    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT
                parcel_id, county_fips, s_legal,
                sec, twn, rng,
                jv, arv_estimate, tot_lvg_area,
                phy_addr1, phy_zipcd
            FROM properties
            WHERE mqi_qualified = true
            AND county_fips = :fips
        """), {"fips": COUNTY_FIPS})
        rows = result.fetchall()

    legal_index: dict[str, dict] = {}
    str_index: dict[str, list] = {}

    for row in rows:
        parcel_data = {
            "parcel_id":    row.parcel_id,
            "county_fips":  row.county_fips,
            "jv":           row.jv,
            "arv_estimate": row.arv_estimate,
            "tot_lvg_area": row.tot_lvg_area,
            "phy_addr1":    row.phy_addr1,
            "phy_zipcd":    row.phy_zipcd,
        }

        # s_legal index — normalize for fuzzy matching
        if row.s_legal:
            norm = re.sub(r"\s+", " ", row.s_legal.upper().strip())
            legal_index[norm] = parcel_data

        # SEC/TWN/RNG index — for parcels without subdivision data
        if row.sec and row.twn and row.rng:
            str_key = f"{row.sec.strip()}|{row.twn.strip()}|{row.rng.strip()}"
            if str_key not in str_index:
                str_index[str_key] = []
            str_index[str_key].append(parcel_data)

    logger.info(
        "Indexes built — legal_index=%d entries str_index=%d keys",
        len(legal_index), len(str_index),
    )
    return legal_index, str_index


def _match_parcel(
    parsed: dict,
    legal_index: dict,
    str_index: dict,
) -> tuple[dict | None, str]:
    """
    Attempt to match a parsed lis pendens record to a parcel.

    Strategy:
        1. If LOT + BLK + SUB present: build query string and fuzzy-match
           against s_legal index using rapidfuzz
        2. If SEC + TWP + RGE present: look up str_index
           (may return multiple parcels — logs ambiguity, returns first)
        3. Otherwise: return None with reason 'no_legal_data'

    Returns:
        (parcel_dict | None, match_method)
        match_method: 'exact_legal' | 'fuzzy_legal' | 'str' | 'none'
    """
    lot = parsed.get("lot")
    blk = parsed.get("block")
    sub = parsed.get("subdivision")
    sec = parsed.get("sec")
    twp = parsed.get("twp")
    rge = parsed.get("rge")

    # ── Strategy 1 — Subdivision fuzzy match ────────────────────────── #
    if sub:
        # Build a query string resembling NAL s_legal format
        # NAL format: "LT 22 BLK 39 MONTCLAIR UN 7" (truncated to 30 chars)
        # LandmarkWeb: "LOT:22 BLK:39 SUB:MONTCLAIR UN 7"
        # Normalize to: "LT 22 BLK 39 MONTCLAIR UN 7"
        lot_norm = lot.replace("/", " ").strip() if lot else ""
        blk_norm = blk.strip() if blk else ""
        sub_norm  = sub.strip()

        # Try multiple query formats — NAL uses abbreviated forms
        queries = []
        if lot_norm and blk_norm:
            queries.append(f"LT {lot_norm} BLK {blk_norm} {sub_norm}")
            queries.append(f"LTS {lot_norm} BLK {blk_norm} {sub_norm}")
            queries.append(f"LOT {lot_norm} BLK {blk_norm} {sub_norm}")
        else:
            queries.append(sub_norm)

        try:
            from rapidfuzz import process as fuzz_process, fuzz

            for query in queries:
                query_norm = re.sub(r"\s+", " ", query.upper().strip())
                # Build string-only choices dict for rapidfuzz
                # legal_index keys ARE the normalized s_legal strings
                legal_choices = {k: k for k in legal_index}
                match_result = fuzz_process.extractOne(
                    query_norm,
                    legal_choices,
                    scorer=fuzz.token_sort_ratio,
                    score_cutoff=FUZZY_THRESHOLD,
                )
                if match_result:
                    matched_key = match_result[2]
                    return legal_index[matched_key], "fuzzy_legal"

        except ImportError:
            logger.warning("rapidfuzz not available — fuzzy matching disabled")

    # ── Strategy 2 — Section/Township/Range match ────────────────────── #
    if sec and twp and rge:
        # Normalize TWP/RGE — LandmarkWeb uses "3N"/"31W", NAL uses "3N"/"31W"
        # Strip direction suffix for matching if needed
        twp_norm = re.sub(r"[NS]$", "", twp.strip())
        rge_norm = re.sub(r"[EW]$", "", rge.strip())

        # Try exact match first
        str_key = f"{sec.strip()}|{twp.strip()}|{rge.strip()}"
        if str_key in str_index:
            parcels = str_index[str_key]
            if len(parcels) == 1:
                return parcels[0], "str"
            else:
                logger.debug(
                    "STR match ambiguous — %d parcels for key %s",
                    len(parcels), str_key,
                )
                return None, "str_ambiguous"

        # Try without direction suffix
        str_key_bare = f"{sec.strip()}|{twp_norm}|{rge_norm}"
        for key in str_index:
            key_parts = key.split("|")
            if len(key_parts) == 3:
                k_sec = key_parts[0]
                k_twp = re.sub(r"[NS]$", "", key_parts[1])
                k_rge = re.sub(r"[EW]$", "", key_parts[2])
                if k_sec == sec.strip() and k_twp == twp_norm and k_rge == rge_norm:
                    parcels = str_index[key]
                    if len(parcels) == 1:
                        return parcels[0], "str"

    return None, "no_match"


# ── deduplication ──────────────────────────────────────────────────────────

def _get_existing_cfns(engine) -> set[int]:
    """Load all CFNs already recorded in listing_events for this source."""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT DISTINCT (raw_listing_json->>'cfn')::bigint AS cfn
            FROM listing_events
            WHERE source = :source
            AND raw_listing_json->>'cfn' IS NOT NULL
        """), {"source": SOURCE_NAME})
        return {row.cfn for row in result.fetchall() if row.cfn}


# ── main parse function ────────────────────────────────────────────────────

def parse_lis_pendens_file(
    filepath: Path,
    engine,
    dry_run: bool,
) -> dict:
    """
    Parse a single LandmarkWeb Excel export file and write listing_events.

    Returns summary dict with counts.
    """
    logger.info("Parsing file: %s", filepath.name)

    # ── Load Excel ──────────────────────────────────────────────────── #
    try:
        df = pd.read_excel(filepath, dtype=str)
    except Exception as exc:
        logger.error("Failed to read Excel file %s: %s", filepath, exc)
        return {"error": str(exc)}

    # Normalize column names — strip whitespace
    df.columns = [c.strip() for c in df.columns]

    # Keep only LIS PENDENS rows — file may contain other doc types
    if "Doc Type" in df.columns:
        df = df[df["Doc Type"].str.strip().str.upper() == "LIS PENDENS"].copy()

    logger.info("Found %d lis pendens rows in file", len(df))

    if df.empty:
        logger.warning("No lis pendens rows found in %s", filepath.name)
        return {"read": 0, "matched": 0, "inserted": 0, "skipped": 0, "unmatched": 0}

    # ── Load indexes and existing CFNs ──────────────────────────────── #
    legal_index, str_index = _build_legal_index(engine)
    existing_cfns = _get_existing_cfns(engine)
    logger.info("Existing CFNs in DB: %d", len(existing_cfns))

    # ── Get active filter profile id ───────────────────────────────── #
    with engine.connect() as conn:
        fp_result = conn.execute(text("""
            SELECT id FROM filter_profiles
            WHERE county_fips = :fips AND is_active = true
            LIMIT 1
        """), {"fips": COUNTY_FIPS})
        fp_row = fp_result.fetchone()
        filter_profile_id = fp_row.id if fp_row else None

    # ── Process rows ────────────────────────────────────────────────── #
    stats = {
        "read": 0, "matched": 0, "inserted": 0,
        "skipped_duplicate": 0, "unmatched": 0,
        "match_methods": {},
    }

    insert_sql = text("""
        INSERT INTO listing_events (
            county_fips, parcel_id, signal_tier, signal_type,
            listing_type, list_date, source, listing_agent_name,
            arv_estimate, arv_source,
            filter_profile_id, workflow_status,
            raw_listing_json, scraped_at, created_at, updated_at
        ) VALUES (
            :county_fips, :parcel_id, :signal_tier, :signal_type,
            :listing_type, :list_date, :source, :listing_agent_name,
            :arv_estimate, :arv_source,
            :filter_profile_id, :workflow_status,
            :raw_listing_json, :scraped_at, NOW(), NOW()
        )
    """)

    # Group rows — LandmarkWeb repeats the primary row data across
    # multiple rows for multi-defendant records. Group by CFN.
    # The first row with a non-null Status is the primary record.
    primary_rows = df[df["Status"].notna() & (df["Status"].str.strip() != "")].copy()

    for _, row in primary_rows.iterrows():
        stats["read"] += 1

        # ── CFN deduplication ────────────────────────────────────── #
        try:
            cfn = int(str(row.get("CFN", "")).strip())
        except (ValueError, TypeError):
            logger.warning("Invalid CFN on row %d — skipping", stats["read"])
            continue

        if cfn in existing_cfns:
            stats["skipped_duplicate"] += 1
            logger.debug("CFN %d already in DB — skipping", cfn)
            continue

        # ── Parse fields ─────────────────────────────────────────── #
        legal_raw   = str(row.get("Legal", "") or "")
        parsed      = _parse_legal(legal_raw)
        owner_name  = _extract_owner_name(str(row.get("Reverse Name", "") or ""))
        lender_name = str(row.get("Direct Name", "") or "").strip()

        record_date_raw = row.get("Record Date", "")
        record_date: date | None = None
        if record_date_raw and str(record_date_raw).strip():
            try:
                record_date = pd.to_datetime(record_date_raw).date()
            except Exception:
                pass

        book = str(row.get("Book", "") or "").strip()
        page = str(row.get("Page", "") or "").strip()
        listing_url = (
            f"https://dory.escambiaclerk.com/LandmarkWeb/search/index"
            f"?CFN={cfn}"
            if cfn else None
        )

        # ── Parcel match ─────────────────────────────────────────── #
        parcel, match_method = _match_parcel(parsed, legal_index, str_index)
        stats["match_methods"][match_method] = (
            stats["match_methods"].get(match_method, 0) + 1
        )

        if parcel is None:
            stats["unmatched"] += 1
            logger.info(
                "Unmatched | CFN=%d method=%s case=%s legal=%s",
                cfn, match_method,
                parsed.get("case_number", ""),
                legal_raw[:80].replace("\n", " "),
            )
            continue

        stats["matched"] += 1

        # ── Build raw_listing_json ────────────────────────────────── #
        raw_json = {
            "cfn":          cfn,
            "case_number":  parsed.get("case_number"),
            "lender":       lender_name,
            "owner_name":   owner_name,
            "record_date":  str(record_date) if record_date else None,
            "book":         book,
            "page":         page,
            "legal_parsed": parsed,
            "match_method": match_method,
            "source_file":  filepath.name,
        }

        payload = {
            "county_fips":       parcel["county_fips"],
            "parcel_id":         parcel["parcel_id"],
            "signal_tier":       SIGNAL_TIER,
            "signal_type":       SIGNAL_TYPE,
            "listing_type":      None,
            "list_date":         record_date,
            "source":            SOURCE_NAME,
            "listing_agent_name": lender_name[:200] if lender_name else None,
            "arv_estimate":      parcel.get("arv_estimate"),
            "arv_source":        "JV",
            "filter_profile_id": filter_profile_id,
            "workflow_status":   "NEW",
            "raw_listing_json":  json.dumps(raw_json),
            "scraped_at":        datetime.now(tz=timezone.utc),
        }

        if dry_run:
            logger.info(
                "[DRY-RUN] Would insert | CFN=%d parcel=%s method=%s "
                "case=%s owner=%s",
                cfn, parcel["parcel_id"], match_method,
                parsed.get("case_number", ""), owner_name,
            )
            stats["inserted"] += 1
            continue

        # ── Insert ───────────────────────────────────────────────── #
        try:
            with engine.begin() as conn:
                conn.execute(insert_sql, payload)
            existing_cfns.add(cfn)  # Prevent re-insert within same run
            stats["inserted"] += 1
        except Exception as exc:
            logger.error("Insert failed for CFN=%d: %s", cfn, exc)

    return stats


# ── directory scanner ──────────────────────────────────────────────────────

def run_lis_pendens_import(
    dry_run: bool,
    specific_file: Path | None,
) -> None:
    """
    Process all unprocessed Excel files in the lis_pendens staging directory,
    or a single specified file.
    """
    t_start = time.time()
    engine = create_engine(settings.sync_database_url, echo=False)

    if specific_file:
        files = [specific_file]
    else:
        files = sorted(STAGING_DIR.glob("*.xlsx")) + sorted(STAGING_DIR.glob("*.xls"))

    if not files:
        logger.info("No Excel files found in %s — nothing to process.", STAGING_DIR)
        return

    logger.info("Found %d file(s) to process", len(files))

    total_stats = {
        "read": 0, "matched": 0, "inserted": 0,
        "skipped_duplicate": 0, "unmatched": 0,
    }

    for filepath in files:
        logger.info("--- Processing: %s ---", filepath.name)
        stats = parse_lis_pendens_file(filepath, engine, dry_run)
        for key in total_stats:
            total_stats[key] += stats.get(key, 0)
        logger.info(
            "File complete | read=%d matched=%d inserted=%d "
            "skipped=%d unmatched=%d",
            stats.get("read", 0),
            stats.get("matched", 0),
            stats.get("inserted", 0),
            stats.get("skipped_duplicate", 0),
            stats.get("unmatched", 0),
        )
        if "match_methods" in stats:
            logger.info("Match methods: %s", stats["match_methods"])

    elapsed = time.time() - t_start
    logger.info(
        "Lis pendens import complete | "
        "read=%d matched=%d inserted=%d skipped=%d unmatched=%d duration=%.1fs",
        total_stats["read"], total_stats["matched"], total_stats["inserted"],
        total_stats["skipped_duplicate"], total_stats["unmatched"], elapsed,
    )


# ── CLI ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse LandmarkWeb lis pendens Excel exports into listing_events."
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

    run_lis_pendens_import(
        dry_run=args.dry_run,
        specific_file=args.file,
    )


if __name__ == "__main__":
    main()
