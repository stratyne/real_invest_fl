"""
real_invest_fl/scrapers/auction_com.py
---------------------------------------
Auction.com Escambia County FL scraper.

Fetches active listings from the Auction.com GraphQL API
(https://graph.auction.com/graphql) and inserts matched records
into listing_events.

Transport: requests (plain HTTP POST — no browser required).
The GraphQL endpoint is a standard JSON API. Playwright was used
only during the one-time investigation to intercept the network
traffic and identify the query structure. The production scraper
calls the API directly.

Filtering:
    The API is queried with property_state=FL and property_county=Escambia
    but returns a 50-mile radius result set (~73 records) that includes
    Alabama Escambia County and adjacent counties. We filter server-side
    on country_primary_subdivision=FL and country_secondary_subdivision
    (case-insensitive) == 'escambia'.

Parcel matching:
    Three-level address fallback identical to zillow_foreclosure_parser.py:
        Level 1 — Exact normalized street + ZIP
        Level 2 — Unit suffix normalization (#4A -> 4A, APT -> bare unit)
        Level 3 — Street prefix LIKE match, single result or REVIEW flag

Deduplication:
    listing_id (Auction.com's internal ID) stored in mls_number.
    Same listing_id = skip. New listing_id = insert.
    Price changes on the same listing_id = insert new row (event log pattern).

Bed/bath enrichment:
    If matched parcel has NULL bedrooms/bathrooms, update properties
    with values from the listing. bed_bath_source = 'auction_com'.
    total_bedrooms/total_bathrooms == 0 treated as NULL (data sentinel).

Signal classification:
    signal_tier = 2 (public aggregator)
    signal_type mapped from listing_configuration.asset_type:
        BANK_OWNED      -> 'bank_owned'
        FORECLOSURE     -> 'foreclosure'
        PRIVATE_SELLER  -> 'private_seller'
        (anything else) -> 'auction'

robots.txt: /residential/* is NOT disallowed. Only /foreclosures/*,
/bank-owned/*, and admin paths are blocked. This scraper targets
/residential/ URLs only and makes API calls, not page requests.

ETHICAL / LEGAL NOTICE:
    This scraper calls a public-facing GraphQL API that serves the same
    data visible to any anonymous user on auction.com. No authentication
    is required or used. No rate limits are exceeded. Data is used solely
    for private investment research.
"""
from __future__ import annotations

import json
import logging
import re
import sys
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from sqlalchemy import create_engine, text

# ── path bootstrap ─────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import settings  # noqa: E402

# ── logging ────────────────────────────────────────────────────────────────
logger = logging.getLogger("auction_com_scraper")

# ── constants ──────────────────────────────────────────────────────────────
COUNTY_FIPS   = "12033"
SIGNAL_TIER   = 2
SOURCE_NAME   = "auction_com"
API_URL       = "https://graph.auction.com/graphql"

# Escambia County FL centroid — used by the API for radius search
GEO_LOCATION  = "30.6389408,-87.3413599"

# Polite delay between retries (seconds)
REQUEST_TIMEOUT  = 30
REQUEST_DELAY    = 3.0

# Sentinel value — Auction.com uses 0 for missing bed/bath/year data
MISSING_SENTINEL = 0

# ── GraphQL query (verbatim from browser network capture 2026-04-28) ───────
_GQL_QUERY = """
      fragment ListingCardFields on Listing {
        __typename
        listing_id
        urn
        listing_status_group
        listing_status
        listing_status_label(intent: SEARCH)
        primary_photo
        primary_property_id
        listing_photos_count
        listing_page_path
        is_hot
        formatted_address(format: DOUBLE_LINE)

        listing_configuration {
          product_type
          is_reserve_displayed
          broker_commission
          financing_available
          buyer_premium_available
          interior_access_allowed
          occupancy_status
          asset_type
          is_first_look_enabled
          is_direct_offer_enabled
          is_third_party_online
        }

        attribution_source {
          origin_code
        }

        venue {
          venue_type
        }

        event {
          event_code
          trustee_sale
        }

        valuation {
          seller_current_value_amount
        }

        seller_property {
          street_description
          municipality
          country_primary_subdivision
          country_secondary_subdivision
          postal_code
        }

        program_configuration {
          program_enrollment_code
        }

        primary_property {
          property_id
          summary {
            total_bedrooms
            total_bathrooms
            square_footage
            lot_size
            year_built
            valuation
            structure_type_code
            structure_type_group
            address {
              coordinates {
                lon
                lat
              }
            }
          }
          is_newly_listed
        }

        auction {
          start_date
          end_date
          starting_bid
          is_online
          visible_auction_start_date_time
        }

        marketing_tags {
          tag
        }

        listing_summary {
          is_remote_bid_enabled
          show_opening_bid
        }

        external_information(resolvePolicy: CACHE_ONLY) {
          collateral {
            summary {
              estimated
              low
              high
              type
            }
          }
        }
      }

    query resiSearch_blueprint_seekListingsFromFilters(
        $filters: ListingCompatabilityFilters!,
        $aggregationFields: [String!]!,
        $requiresAggregation: Boolean!
      ) {
        seek_listings_from_filters(filters: $filters) {
          total_count
          total_pages
          size
          current_page
          aggregation(fields: $aggregationFields) @include(if: $requiresAggregation)
          content {
            ...ListingCardFields
          }
        }
      }
"""

_GQL_VARIABLES = {
    "filters": {
        "property_state":    "FL",
        "property_county":   "Escambia",
        "geo_location":      GEO_LOCATION,
        "listing_type":      "active",
        "sort":              "auction_date_order,resi_sort_v2",
        "limit":             500,
        "nearby_search":     "y",
        "nearby_search_radius": 50,
        "version":           1,
        "offset":            0,
    },
    "aggregationFields": [
        "primary_property_summary.structure_type_code.keyword",
        "listing_summary.is_remote_bid_enabled",
        "seller_property.country_secondary_subdivision.keyword",
    ],
    "requiresAggregation": True,
}


# ── helpers ────────────────────────────────────────────────────────────────

def _make_headers() -> dict:
    """Build request headers. x-cid must be a fresh UUID each request."""
    return {
        "auction-graph-source": "auctioncom",
        "accept":               "application/json",
        "content-type":         "application/json",
        "x-cid":                str(uuid.uuid4()),
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "referer": "https://www.auction.com/",
    }


def _fetch_listings() -> list[dict]:
    """
    POST the GraphQL query and return the content array.
    Returns empty list on any error.
    """
    payload = {
        "query":     _GQL_QUERY,
        "variables": _GQL_VARIABLES,
    }
    try:
        resp = requests.post(
            API_URL,
            headers=_make_headers(),
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        content = (
            data
            .get("data", {})
            .get("seek_listings_from_filters", {})
            .get("content", [])
        )
        total = (
            data
            .get("data", {})
            .get("seek_listings_from_filters", {})
            .get("total_count", 0)
        )
        logger.info(
            "API returned %d total listings, %d in content array",
            total, len(content),
        )
        return content
    except requests.exceptions.HTTPError as exc:
        logger.error("GraphQL fetch failed: %s", exc)
        logger.error("Response body: %s", exc.response.text[:2000])
        return []


def _is_escambia_fl(listing: dict) -> bool:
    """
    Return True only if the listing is in Escambia County, Florida.
    The 50-mile radius search returns Alabama Escambia County and
    adjacent FL/AL counties — filter them all out here.
    """
    sp = listing.get("seller_property") or {}
    state  = (sp.get("country_primary_subdivision") or "").upper().strip()
    county = (sp.get("country_secondary_subdivision") or "").upper().strip()
    return state == "FL" and county == "ESCAMBIA"


def _signal_type(listing: dict) -> str:
    """Map asset_type to signal_type string."""
    asset_type = (
        (listing.get("listing_configuration") or {})
        .get("asset_type", "")
        or ""
    ).upper()
    return {
        "BANK_OWNED":     "bank_owned",
        "FORECLOSURE":    "foreclosure",
        "PRIVATE_SELLER": "private_seller",
    }.get(asset_type, "auction")


def _safe_int(value, sentinel: int = MISSING_SENTINEL) -> Optional[int]:
    """Return None if value is None or equals the sentinel (0 = missing)."""
    if value is None:
        return None
    try:
        v = int(value)
        return None if v == sentinel else v
    except (TypeError, ValueError):
        return None


def _safe_float(value, sentinel: float = float(MISSING_SENTINEL)) -> Optional[float]:
    """Return None if value is None or equals the sentinel."""
    if value is None:
        return None
    try:
        v = float(value)
        return None if v == sentinel else v
    except (TypeError, ValueError):
        return None


def _parse_auction_date(listing: dict) -> Optional[date]:
    """
    Return the most useful date for list_date.
    Prefer visible_auction_start_date_time, fall back to start_date.
    """
    auction = listing.get("auction") or {}
    raw = auction.get("visible_auction_start_date_time") or auction.get("start_date")
    if not raw:
        return None
    try:
        # ISO 8601 with Z suffix
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except Exception:
        return None

# Street suffix abbreviation map — expand NAL-style abbreviations
# OR contract verbose source strings to match NAL
# NAL uses abbreviated forms — we normalize incoming to match NAL
_STREET_SUFFIX_MAP = {
    "ROAD":      "RD",
    "STREET":    "ST",
    "AVENUE":    "AVE",
    "BOULEVARD": "BLVD",
    "DRIVE":     "DR",
    "COURT":     "CT",
    "PLACE":     "PL",
    "LANE":      "LN",
    "CIRCLE":    "CIR",
    "TRAIL":     "TRL",
    "TERRACE":   "TER",
    "HIGHWAY":   "HWY",
    "PARKWAY":   "PKWY",
    "EXPRESSWAY": "EXPY",
    "FREEWAY":   "FWY",
}

# Directional prefixes that appear in source data but not in NAL
_DIRECTIONAL_PREFIXES = {
    "NORTH", "SOUTH", "EAST", "WEST",
    "N", "S", "E", "W",
}

def _normalize_street(street: str) -> str:
    """
    Minimal normalization for DB matching against NAL phy_addr1.
    More sophisticated normalization is deferred to listing_matcher.py
    and real_invest_fl/utils/text.py.
    """
    # Inject space between digit run and letter (2301W -> 2301 W)
    street = re.sub(r"(\d)([A-Za-z])", r"\1 \2", street)
    # Collapse whitespace and upper-case
    return re.sub(r"\s+", " ", street.upper().strip())

def _build_address(listing: dict) -> tuple[str, str, Optional[str]]:
    """
    Return (full_address, street_normalized, zip_code) from seller_property.
    street_normalized is cleaned for DB matching against phy_addr1.
    """
    sp = listing.get("seller_property") or {}
    street    = (sp.get("street_description") or "").strip()
    city      = (sp.get("municipality") or "").strip()
    state     = (sp.get("country_primary_subdivision") or "FL").strip()
    zip_code  = (sp.get("postal_code") or "").strip() or None

    full = f"{street}, {city}, {state} {zip_code}".strip(", ")
    street_norm = _normalize_street(street)
    return full, street_norm, zip_code


def _listing_url(listing: dict) -> Optional[str]:
    path = listing.get("listing_page_path") or ""
    return f"https://www.auction.com{path}" if path else None


# ── parcel lookup (mirrors zillow_foreclosure_parser._lookup_parcel) ───────

def _lookup_parcel(conn, street: str, zip_code: Optional[str]) -> Optional[dict]:
    """
    Three-level address fallback against properties table.
    Identical logic to zillow_foreclosure_parser._lookup_parcel.
    """
    select_cols = (
        "parcel_id, county_fips, jv, arv_estimate, "
        "tot_lvg_area, bedrooms, bathrooms"
    )

    def _fetch_one(where_clause: str, params: dict) -> Optional[object]:
        return conn.execute(
            text(
                f"SELECT {select_cols} FROM properties "
                f"WHERE county_fips = :fips AND {where_clause} LIMIT 1"
            ),
            {"fips": COUNTY_FIPS, **params},
        ).fetchone()

    def _fetch_all(where_clause: str, params: dict) -> list:
        return conn.execute(
            text(
                f"SELECT {select_cols} FROM properties "
                f"WHERE county_fips = :fips AND {where_clause}"
            ),
            {"fips": COUNTY_FIPS, **params},
        ).fetchall()

    def _row_to_dict(row) -> dict:
        return {
            "parcel_id":    row.parcel_id,
            "county_fips":  row.county_fips,
            "jv":           row.jv,
            "arv_estimate": row.arv_estimate,
            "tot_lvg_area": row.tot_lvg_area,
            "bedrooms":     row.bedrooms,
            "bathrooms":    row.bathrooms,
        }

    # Level 1 — exact match
    if zip_code:
        row = _fetch_one(
            "UPPER(TRIM(phy_addr1)) = :street AND phy_zipcd = :zip",
            {"street": street, "zip": zip_code},
        )
        if row:
            return _row_to_dict(row)

    row = _fetch_one(
        "UPPER(TRIM(phy_addr1)) = :street",
        {"street": street},
    )
    if row:
        return _row_to_dict(row)

    # Level 2 — unit suffix normalization (#4A -> 4A, APT -> bare unit)
    unit_match = re.search(
        r"^(.*?)\s*(?:#|APT\.?\s*|UNIT\s+)([A-Z0-9]+)\s*$",
        street,
        re.IGNORECASE,
    )
    if unit_match:
        base = unit_match.group(1).strip()
        unit = unit_match.group(2).strip()
        normalized_with_unit = f"{base} {unit}"

        if zip_code:
            row = _fetch_one(
                "UPPER(TRIM(phy_addr1)) = :street AND phy_zipcd = :zip",
                {"street": normalized_with_unit, "zip": zip_code},
            )
            if row:
                return _row_to_dict(row)

        row = _fetch_one(
            "UPPER(TRIM(phy_addr1)) = :street",
            {"street": normalized_with_unit},
        )
        if row:
            return _row_to_dict(row)

        base_street = base
    else:
        base_street = street

    # Level 3 — street prefix LIKE, single result or REVIEW flag
    prefix_match = re.match(r"^(\d+\s+\S+(?:\s+\S+)?)", base_street)
    if prefix_match:
        prefix = prefix_match.group(1).strip()

        if zip_code:
            rows = _fetch_all(
                "UPPER(TRIM(phy_addr1)) LIKE :prefix AND phy_zipcd = :zip",
                {"prefix": f"{prefix}%", "zip": zip_code},
            )
        else:
            rows = _fetch_all(
                "UPPER(TRIM(phy_addr1)) LIKE :prefix",
                {"prefix": f"{prefix}%"},
            )

        if len(rows) == 1:
            return _row_to_dict(rows[0])

        if len(rows) > 1:
            parcel_ids = ", ".join(r.parcel_id for r in rows)
            print(
                f"[REVIEW] MULTI-UNIT — {len(rows)} parcels match "
                f"'{prefix}%' ZIP={zip_code} — "
                f"parcels: {parcel_ids} — manual selection required"
            )

    return None


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


def _get_existing_listing_ids(conn) -> set[str]:
    """Load all listing_ids already in listing_events for this source."""
    rows = conn.execute(
        text(
            "SELECT mls_number FROM listing_events "
            "WHERE source = :src AND mls_number IS NOT NULL"
        ),
        {"src": SOURCE_NAME},
    ).fetchall()
    return {r[0] for r in rows}


def _enrich_parcel_bed_bath(
    conn,
    parcel_id: str,
    county_fips: str,
    bedrooms: Optional[int],
    bathrooms: Optional[float],
) -> bool:
    """Update properties bed/bath if currently NULL. Returns True if updated."""
    if bedrooms is None and bathrooms is None:
        return False
    result = conn.execute(
        text(
            "UPDATE properties "
            "SET bedrooms = COALESCE(bedrooms, :beds), "
            "    bathrooms = COALESCE(bathrooms, :baths), "
            "    bed_bath_source = COALESCE(bed_bath_source, :src) "
            "WHERE parcel_id = :pid "
            "AND county_fips = :fips "
            "AND (bedrooms IS NULL OR bathrooms IS NULL)"
        ),
        {
            "beds":  bedrooms,
            "baths": bathrooms,
            "src":   SOURCE_NAME,
            "pid":   parcel_id,
            "fips":  county_fips,
        },
    )
    return result.rowcount > 0


# ── main run function ──────────────────────────────────────────────────────

def run(engine=None) -> dict:
    """
    Fetch Auction.com Escambia County FL listings, match to MQI parcels,
    and insert new listing_events records.

    Returns summary dict with counts.
    """
    if engine is None:
        engine = create_engine(settings.sync_database_url, echo=False)

    t_start = time.time()
    stats = {
        "fetched":    0,
        "escambia_fl": 0,
        "matched":    0,
        "inserted":   0,
        "skipped":    0,
        "unmatched":  0,
        "enriched":   0,
    }

    # ── Fetch from API ──────────────────────────────────────────────── #
    all_listings = _fetch_listings()
    stats["fetched"] = len(all_listings)

    # ── Filter to Escambia FL only ──────────────────────────────────── #
    fl_listings = [l for l in all_listings if _is_escambia_fl(l)]
    stats["escambia_fl"] = len(fl_listings)
    logger.info(
        "Filtered to %d Escambia FL listings from %d total",
        len(fl_listings), len(all_listings),
    )

    if not fl_listings:
        logger.info("No Escambia FL listings found — nothing to insert.")
        return stats

    today = date.today()

    with engine.begin() as conn:
        existing_ids     = _get_existing_listing_ids(conn)
        filter_profile_id = _get_filter_profile_id(conn)

        for listing in fl_listings:
            listing_id = str(listing.get("listing_id", "")).strip()
            if not listing_id:
                logger.warning("Listing with no listing_id — skipping")
                stats["unmatched"] += 1
                continue

            # ── Dedup ─────────────────────────────────────────────── #
            if listing_id in existing_ids:
                logger.debug("Duplicate listing_id=%s — skipping", listing_id)
                stats["skipped"] += 1
                continue

            # ── Build address components ──────────────────────────── #
            full_address, street_norm, zip_code = _build_address(listing)

            if not street_norm:
                print(
                    f"[REVIEW] listing_id={listing_id} has no street address"
                )
                stats["unmatched"] += 1
                continue

            # ── Parcel match ──────────────────────────────────────── #
            parcel = _lookup_parcel(conn, street_norm, zip_code)

            if parcel is None:
                print(
                    f"[REVIEW] No parcel match for listing_id={listing_id} "
                    f"address={full_address!r}"
                )
                stats["unmatched"] += 1
                continue

            stats["matched"] += 1

            # ── Extract fields ────────────────────────────────────── #
            summary   = (listing.get("primary_property") or {}).get("summary") or {}
            auction   = listing.get("auction") or {}
            lc        = listing.get("listing_configuration") or {}

            bedrooms  = _safe_int(summary.get("total_bedrooms"))
            bathrooms = _safe_float(summary.get("total_bathrooms"))
            sqft      = _safe_int(summary.get("square_footage"))
            year_built = _safe_int(summary.get("year_built"))
            starting_bid = auction.get("starting_bid")
            list_price = int(starting_bid) if starting_bid is not None else None
            list_date  = _parse_auction_date(listing)
            end_date   = None
            end_raw    = auction.get("end_date")
            if end_raw:
                try:
                    end_date = datetime.fromisoformat(
                        end_raw.replace("Z", "+00:00")
                    ).date()
                except Exception:
                    pass

            price_per_sqft = None
            if list_price and sqft and sqft > 0:
                price_per_sqft = round(list_price / sqft, 2)

            signal_type = _signal_type(listing)
            listing_url = _listing_url(listing)

            marketing_tags = [
                t.get("tag") for t in (listing.get("marketing_tags") or [])
                if t.get("tag")
            ]

            # ── Bed/bath enrichment ───────────────────────────────── #
            if parcel["bedrooms"] is None or parcel["bathrooms"] is None:
                enriched = _enrich_parcel_bed_bath(
                    conn,
                    parcel["parcel_id"],
                    parcel["county_fips"],
                    bedrooms,
                    bathrooms,
                )
                if enriched:
                    stats["enriched"] += 1

            # ── Build raw_listing_json ────────────────────────────── #
            raw_json = {
                "listing_id":       listing_id,
                "listing_status":   listing.get("listing_status"),
                "listing_status_label": listing.get("listing_status_label"),
                "asset_type":       lc.get("asset_type"),
                "product_type":     lc.get("product_type"),
                "occupancy_status": lc.get("occupancy_status"),
                "venue_type":       (listing.get("venue") or {}).get("venue_type"),
                "is_online":        auction.get("is_online"),
                "auction_start":    auction.get("start_date"),
                "auction_end":      auction.get("end_date"),
                "starting_bid":     starting_bid,
                "structure_type":   summary.get("structure_type_code"),
                "year_built":       year_built,
                "sqft":             sqft,
                "bedrooms":         bedrooms,
                "bathrooms":        bathrooms,
                "lot_size":         summary.get("lot_size"),
                "marketing_tags":   marketing_tags,
                "full_address":     full_address,
                "listing_url":      listing_url,
                "scraped_at":       datetime.now(tz=timezone.utc).isoformat(),
            }

            # ── Insert listing_event ──────────────────────────────── #
            conn.execute(
                text("""
                    INSERT INTO listing_events (
                        county_fips, parcel_id,
                        listing_type, list_price, list_date,
                        expiry_date,
                        price_per_sqft,
                        arv_estimate, arv_source,
                        source, signal_tier, signal_type,
                        listing_url,
                        mls_number,
                        workflow_status,
                        filter_profile_id,
                        raw_listing_json,
                        scraped_at, created_at, updated_at
                    ) VALUES (
                        :county_fips, :parcel_id,
                        :listing_type, :list_price, :list_date,
                        :expiry_date,
                        :price_per_sqft,
                        :arv_estimate, :arv_source,
                        :source, :signal_tier, :signal_type,
                        :listing_url,
                        :mls_number,
                        :workflow_status,
                        :filter_profile_id,
                        CAST(:raw_listing_json AS jsonb),
                        :scraped_at, NOW(), NOW()
                    )
                """),
                {
                    "county_fips":       parcel["county_fips"],
                    "parcel_id":         parcel["parcel_id"],
                    "listing_type":      signal_type,
                    "list_price":        list_price,
                    "list_date":         list_date,
                    "expiry_date":       end_date,
                    "price_per_sqft":    price_per_sqft,
                    "arv_estimate":      parcel["arv_estimate"],
                    "arv_source":        "JV",
                    "source":            SOURCE_NAME,
                    "signal_tier":       SIGNAL_TIER,
                    "signal_type":       signal_type,
                    "listing_url":       listing_url,
                    "mls_number":        listing_id,
                    "workflow_status":   "new",
                    "filter_profile_id": filter_profile_id,
                    "raw_listing_json":  json.dumps(raw_json),
                    "scraped_at":        datetime.now(tz=timezone.utc),
                },
            )

            existing_ids.add(listing_id)
            stats["inserted"] += 1

    elapsed = time.time() - t_start
    logger.info(
        "Auction.com scrape complete | fetched=%d escambia_fl=%d "
        "matched=%d inserted=%d skipped=%d unmatched=%d "
        "enriched=%d duration=%.1fs",
        stats["fetched"], stats["escambia_fl"],
        stats["matched"], stats["inserted"],
        stats["skipped"], stats["unmatched"],
        stats["enriched"], elapsed,
    )
    return stats
