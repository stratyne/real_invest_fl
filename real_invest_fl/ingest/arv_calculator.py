"""
real_invest_fl/ingest/arv_calculator.py
----------------------------------------
ARV Calculation Pipeline.

Computes and writes ARV-related metrics to the properties table for all
eligible parcels. Eligibility is determined by a two-tier gate:

    Tier 1 — jv IS NOT NULL AND geom IS NOT NULL
        Attempt COMP calculation from parcel_sale_history.
        Fall back to NAL spatial fallback if parcel_sale_history yields
        insufficient comps after both primary and wider pool passes.
        Fall back to raw jv if NAL spatial fallback also yields
        insufficient comps.

    Tier 2 — jv IS NOT NULL AND geom IS NULL
        Skip spatial comp join entirely.
        Write arv_estimate = jv, arv_source = JV_FALLBACK directly.

    Excluded — jv IS NULL
        Skipped entirely. Count logged.

Columns written per parcel:
    jv_per_sqft   — jv / tot_lvg_area (NULL if tot_lvg_area is NULL or zero)
    arv_estimate  — median(sale_price / tot_lvg_area) * subject.tot_lvg_area
                    for COMP path;
                    median(sale_prc1 / tot_lvg_area) * subject.tot_lvg_area
                    for NAL spatial fallback path;
                    jv for raw jv floor path
    arv_source    — 'COMP', 'NAL_COMP', or 'JV_FALLBACK'
    arv_spread    — arv_estimate - list_price - (tot_lvg_area * rehab_cost)
                    NULL when list_price is NULL or tot_lvg_area is NULL

Three-pass comp strategy (Tier 1 parcels only):
    Pass 1 — parcel_sale_history, primary pool:
             qualification_code IN ('Q', 'C'), sale_price >= 10000,
             (instrument_type = 'WD' OR instrument_type IS NULL)
    Pass 2 — parcel_sale_history, wider pool:
             qualification_code IN ('Q', 'C', 'U'), same price/instrument filter
             Scoped to subject parcel only when primary yields < min_comps.
    Pass 3 — NAL embedded fields on neighboring properties:
             qual_cd1 = '01', sale_prc1 >= 10000, same spatial/year/dor_uc filters
             Triggered only when Pass 2 also yields < min_comps.
    Floor  — arv_estimate = jv, arv_source = JV_FALLBACK
             Triggered only when Pass 3 also yields < min_comps.

County pre-flight viability check:
    Counties with fewer than MIN_VIABLE_COMP_POOL qualifying
    parcel_sale_history records (qualification_code IN ('Q', 'C'),
    sale_price >= 10000) skip Pass 1 and Pass 2 entirely and go
    directly to Pass 3 (NAL spatial fallback) then floor if needed.

Usage:
    python -m real_invest_fl.ingest.arv_calculator [options]

Options:
    --dry-run           Compute metrics but do not write to database.
    --force             Recalculate all eligible parcels, even if already done.
    --batch-size N      Rows per transaction batch (default: 500).
    --county FIPS       Restrict run to a single county_fips value.
    --radius MILES      Comp search radius in miles (default: 1.5).
    --min-comps N       Minimum qualifying comps for COMP arv_source (default: 3).
    --year-tolerance N  +/- years built tolerance for comp selection (default: 10).
    --rehab-cost N      Rehab cost per sqft for arv_spread (default: 35.00).
"""

from __future__ import annotations

import argparse
import logging
import statistics
import sys
import time
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, text

# ── path bootstrap ────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import settings  # noqa: E402

# ── logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("arv_calculator")

# ── constants ─────────────────────────────────────────────────────────────────
DEFAULT_BATCH          = 500
DEFAULT_RADIUS_MILES   = 1.5
DEFAULT_MIN_COMPS      = 3
DEFAULT_YEAR_TOLERANCE = 10
DEFAULT_REHAB_COST     = 35.00
MILES_TO_METERS        = 1609.344
MIN_VIABLE_COMP_POOL   = 1000


# ── helpers ───────────────────────────────────────────────────────────────────

def _chunks(lst: list, size: int) -> Iterator[list]:
    """Yield successive chunks of `size` from `lst`."""
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


def _jv_per_sqft(jv: int, tot_lvg_area: int | None) -> Decimal | None:
    """Compute jv / tot_lvg_area. Returns None if area is NULL or zero."""
    if not tot_lvg_area or tot_lvg_area <= 0:
        return None
    return Decimal(jv) / Decimal(tot_lvg_area)


def _arv_spread(
    arv_estimate: int,
    list_price: int | None,
    tot_lvg_area: int | None,
    rehab_cost: float,
) -> int | None:
    """
    Compute arv_spread = arv_estimate - list_price - rehab_cost_estimate.
    Returns None when list_price is NULL or tot_lvg_area is NULL or zero.
    Never substitutes 0 for NULL list_price.
    """
    if list_price is None or tot_lvg_area is None or tot_lvg_area <= 0:
        return None
    rehab_cost_estimate = int(tot_lvg_area * rehab_cost)
    return arv_estimate - list_price - rehab_cost_estimate


def _median_arv_from_ppsf(
    rows: list[dict],
    price_key: str,
    area_key: str,
    subject_area: int,
) -> int | None:
    """
    Compute ARV from a list of comp rows for a single subject parcel.

    Generic over price and area column names to serve both the
    parcel_sale_history path (sale_price / comp_tot_lvg_area) and
    the NAL fallback path (sale_prc1 / tot_lvg_area).

    Rows with NULL or zero area are excluded.
    Returns None if no valid price_per_sqft values can be computed.
    """
    ppsf_values = []
    for row in rows:
        price = row[price_key]
        area  = row[area_key]
        if price and area and area > 0:
            ppsf_values.append(Decimal(price) / Decimal(area))
    if not ppsf_values:
        return None
    median_ppsf = Decimal(str(statistics.median(ppsf_values)))
    return int(
        (median_ppsf * Decimal(subject_area))
        .to_integral_value(rounding=ROUND_HALF_UP)
    )


# ── comp SQL ──────────────────────────────────────────────────────────────────

# Pass 1 / Pass 2 — parcel_sale_history spatial query
_COMP_SQL = text("""
    SELECT
        psh.sale_price,
        p.tot_lvg_area  AS comp_tot_lvg_area
    FROM parcel_sale_history psh
    JOIN properties p
      ON p.county_fips = psh.county_fips
     AND p.parcel_id   = psh.parcel_id
    WHERE psh.county_fips = :county_fips
      AND (
          psh.qualification_code = ANY(:qual_codes)
          OR (psh.qualification_code IS NULL AND psh.instrument_type = 'WD')
      )
      AND psh.sale_price >= 10000
      AND p.dor_uc = :dor_uc
      AND p.eff_yr_blt IS NOT NULL
      AND ABS(p.eff_yr_blt - :subject_eff_yr_blt) <= :year_tolerance
      AND ST_DWithin(
              p.geom::geography,
              ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
              :radius_meters
          )
      AND NOT (p.county_fips = :county_fips AND p.parcel_id = :parcel_id)
""")

# Pass 3 — NAL embedded fields spatial query
# Queries neighboring properties' sale_prc1/qual_cd1 fields.
# qual_cd1 = '01' is the primary qualifying NAL code (arms-length).
# qual_cd2 fallback not included — two-field NAL history is too thin
# to reliably widen; jv floor is preferable to noisy qual_cd2 comps.
_NAL_FALLBACK_SQL = text("""
    SELECT
        p.sale_prc1     AS sale_prc1,
        p.tot_lvg_area  AS tot_lvg_area
    FROM properties p
    WHERE p.county_fips = :county_fips
      AND p.dor_uc = :dor_uc
      AND p.eff_yr_blt IS NOT NULL
      AND ABS(p.eff_yr_blt - :subject_eff_yr_blt) <= :year_tolerance
      AND p.qual_cd1 = '01'
      AND p.sale_prc1 >= 10000
      AND p.tot_lvg_area > 0
      AND p.geom IS NOT NULL
      AND ST_DWithin(
              p.geom::geography,
              ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
              :radius_meters
          )
      AND NOT (p.county_fips = :county_fips AND p.parcel_id = :parcel_id)
""")


# ── county viability pre-flight ───────────────────────────────────────────────

def _check_county_viability(
    conn,
    county_fips_list: list[str],
) -> dict[str, bool]:
    """
    For each county, check whether parcel_sale_history contains at least
    MIN_VIABLE_COMP_POOL qualifying arms-length records.

    Arms-length definition mirrors _COMP_SQL:
        (qualification_code IN ('Q', 'C'))
        OR (qualification_code IS NULL AND instrument_type = 'WD')
        AND sale_price >= 10000

    This ensures counties like Escambia that surface instrument_type
    but not qualification_code are correctly assessed as viable rather
    than being sent directly to Pass 3.

    Returns dict mapping county_fips -> viable (bool).
    """
    result = conn.execute(
        text("""
            SELECT
                county_fips,
                COUNT(*) AS qualifying_count
            FROM parcel_sale_history
            WHERE county_fips = ANY(:fips_list)
              AND (
                  qualification_code IN ('Q', 'C')
                  OR (qualification_code IS NULL AND instrument_type = 'WD')
              )
              AND sale_price >= 10000
            GROUP BY county_fips
        """),
        {"fips_list": county_fips_list},
    )
    counts = {row.county_fips: row.qualifying_count for row in result}

    viability = {}
    for fips in county_fips_list:
        count  = counts.get(fips, 0)
        viable = count >= MIN_VIABLE_COMP_POOL
        viability[fips] = viable
        status = "VIABLE" if viable else "BELOW THRESHOLD"
        logger.info(
            "County %s — qualifying comp pool: %d (%s, threshold: %d)",
            fips, count, status, MIN_VIABLE_COMP_POOL,
        )

    return viability


# ── comp engine ───────────────────────────────────────────────────────────────

def _fetch_psh_comps(
    conn,
    subject: dict,
    qual_codes: list[str],
    radius_meters: float,
    year_tolerance: int,
) -> list[dict]:
    """
    Pass 1 / Pass 2 — fetch parcel_sale_history comp candidates
    for a single subject parcel.
    """
    rows = conn.execute(
        _COMP_SQL,
        {
            "county_fips":        subject["county_fips"],
            "qual_codes":         qual_codes,
            "dor_uc":             subject["dor_uc"],
            "subject_eff_yr_blt": subject["eff_yr_blt"],
            "year_tolerance":     year_tolerance,
            "lon":                float(subject["longitude"]),
            "lat":                float(subject["latitude"]),
            "radius_meters":      radius_meters,
            "parcel_id":          subject["parcel_id"],
        },
    )
    return [dict(r._mapping) for r in rows.fetchall()]


def _fetch_nal_comps(
    conn,
    subject: dict,
    radius_meters: float,
    year_tolerance: int,
) -> list[dict]:
    """
    Pass 3 — fetch NAL embedded sale field comp candidates
    for a single subject parcel.
    Uses qual_cd1 = '01' (arms-length) and sale_prc1 >= 10000.
    """
    rows = conn.execute(
        _NAL_FALLBACK_SQL,
        {
            "county_fips":        subject["county_fips"],
            "dor_uc":             subject["dor_uc"],
            "subject_eff_yr_blt": subject["eff_yr_blt"],
            "year_tolerance":     year_tolerance,
            "lon":                float(subject["longitude"]),
            "lat":                float(subject["latitude"]),
            "radius_meters":      radius_meters,
            "parcel_id":          subject["parcel_id"],
        },
    )
    return [dict(r._mapping) for r in rows.fetchall()]


def _compute_comp_arv(
    subject: dict,
    conn,
    radius_meters: float,
    min_comps: int,
    year_tolerance: int,
    viable: bool,
) -> tuple[int, str]:
    """
    Attempt COMP arv calculation for a single subject parcel.

    Returns (arv_estimate, arv_source).

    Three-pass strategy:
        Pass 1 — parcel_sale_history primary pool (Q, C)
                 Skipped for non-viable counties.
        Pass 2 — parcel_sale_history wider pool (Q, C, U)
                 Skipped for non-viable counties.
        Pass 3 — NAL embedded fields (qual_cd1 = '01')
                 Always attempted when Passes 1+2 yield < min_comps.
        Floor  — arv_estimate = jv, arv_source = JV_FALLBACK
    """
    if not subject["tot_lvg_area"] or subject["tot_lvg_area"] <= 0:
        # Cannot compute comp ARV without subject area — skip to floor
        return subject["jv"], "JV_FALLBACK"

    subject_area = subject["tot_lvg_area"]

    if viable:
        # ── Pass 1 — PSH primary pool ─────────────────────────────── #
        primary_comps = _fetch_psh_comps(
            conn, subject,
            qual_codes=["Q", "C"],
            radius_meters=radius_meters,
            year_tolerance=year_tolerance,
        )
        if len(primary_comps) >= min_comps:
            arv = _median_arv_from_ppsf(
                primary_comps, "sale_price", "comp_tot_lvg_area", subject_area,
            )
            if arv is not None:
                return arv, "COMP"

        # ── Pass 2 — PSH wider pool ───────────────────────────────── #
        wider_comps = _fetch_psh_comps(
            conn, subject,
            qual_codes=["Q", "C", "U"],
            radius_meters=radius_meters,
            year_tolerance=year_tolerance,
        )
        if len(wider_comps) >= min_comps:
            arv = _median_arv_from_ppsf(
                wider_comps, "sale_price", "comp_tot_lvg_area", subject_area,
            )
            if arv is not None:
                return arv, "COMP"

    # ── Pass 3 — NAL spatial fallback ────────────────────────────── #
    nal_comps = _fetch_nal_comps(
        conn, subject,
        radius_meters=radius_meters,
        year_tolerance=year_tolerance,
    )
    if len(nal_comps) >= min_comps:
        arv = _median_arv_from_ppsf(
            nal_comps, "sale_prc1", "tot_lvg_area", subject_area,
        )
        if arv is not None:
            return arv, "NAL_COMP"

    # ── Floor — raw jv ────────────────────────────────────────────── #
    return subject["jv"], "JV_FALLBACK"


# ── core pipeline ─────────────────────────────────────────────────────────────

def run_arv_calculation(
    dry_run:        bool,
    force:          bool,
    batch_size:     int,
    county:         str | None,
    radius_miles:   float,
    min_comps:      int,
    year_tolerance: int,
    rehab_cost:     float,
) -> None:
    """
    Full ARV calculation pipeline.

    Steps:
        1.  Connect to database.
        2.  Load eligible parcels (two-tier gate).
        3.  Run county viability pre-flight.
        4.  For each parcel: compute jv_per_sqft, arv_estimate,
            arv_source, arv_spread via three-pass comp strategy.
        5.  Batch-write results.
        6.  Log summary.
    """
    t_start       = time.time()
    radius_meters = radius_miles * MILES_TO_METERS

    logger.info(
        "ARV calculator starting | radius=%.1f mi | min_comps=%d | "
        "year_tolerance=%d | rehab_cost=$%.2f | dry_run=%s | force=%s",
        radius_miles, min_comps, year_tolerance, rehab_cost,
        dry_run, force,
    )

    engine = create_engine(settings.host_sync_database_url, echo=False)

    # ── Step 2 — Load eligible parcels ───────────────────────────────── #
    county_filter = "AND p.county_fips = :county" if county else ""
    resume_filter = "" if force else "AND p.arv_estimate IS NULL"

    fetch_sql = text(f"""
        SELECT
            p.county_fips,
            p.parcel_id,
            p.jv,
            p.tot_lvg_area,
            p.list_price,
            p.dor_uc,
            p.eff_yr_blt,
            p.latitude,
            p.longitude,
            CASE WHEN p.geom IS NOT NULL THEN true ELSE false END AS has_geom
        FROM properties p
        WHERE p.jv IS NOT NULL
          {resume_filter}
          {county_filter}
        ORDER BY p.county_fips, p.parcel_id
    """)

    params: dict = {}
    if county:
        params["county"] = county

    with engine.connect() as conn:
        result  = conn.execute(fetch_sql, params)
        parcels = [dict(r._mapping) for r in result.fetchall()]

    total = len(parcels)
    logger.info("Loaded %d eligible parcels", total)

    if total == 0:
        logger.info("No parcels require ARV calculation — all up to date.")
        return

    # ── Step 3 — County viability pre-flight ─────────────────────────── #
    county_fips_list = list({p["county_fips"] for p in parcels})

    with engine.connect() as conn:
        viability = _check_county_viability(conn, county_fips_list)

    viable_counties    = {f for f, v in viability.items() if v}
    nonviable_counties = {f for f, v in viability.items() if not v}

    if nonviable_counties:
        logger.info(
            "Counties below comp pool threshold — Passes 1+2 skipped, "
            "NAL spatial fallback (Pass 3) attempted directly: %s",
            sorted(nonviable_counties),
        )

    # ── Step 4 — Compute metrics ──────────────────────────────────────── #
    logger.info("Computing ARV metrics...")

    computed        = []
    comp_count      = 0
    fallback_count  = 0
    no_geom_count   = 0
    no_sqft_count   = 0

    with engine.connect() as conn:
        for i, parcel in enumerate(parcels, start=1):
            jv           = parcel["jv"]
            tot_lvg_area = parcel["tot_lvg_area"]
            list_price   = parcel["list_price"]
            has_geom     = parcel["has_geom"]
            fips         = parcel["county_fips"]

            # jv_per_sqft — independent of comp path
            jv_psf = _jv_per_sqft(jv, tot_lvg_area)
            if tot_lvg_area is None or tot_lvg_area <= 0:
                no_sqft_count += 1

            if not has_geom:
                # Tier 2 — no geom, cannot run any spatial query
                arv_estimate = jv
                arv_source   = "JV_FALLBACK"
                no_geom_count += 1
                fallback_count += 1
            else:
                # Tier 1 — three-pass comp strategy
                arv_estimate, arv_source = _compute_comp_arv(
                    parcel, conn,
                    radius_meters=radius_meters,
                    min_comps=min_comps,
                    year_tolerance=year_tolerance,
                    viable=fips in viable_counties,
                )
                if arv_source == "COMP":
                    comp_count += 1
                else:
                    fallback_count += 1

            spread = _arv_spread(
                arv_estimate, list_price, tot_lvg_area, rehab_cost,
            )

            computed.append({
                "county_fips":  fips,
                "parcel_id":    parcel["parcel_id"],
                "jv_per_sqft":  jv_psf,
                "arv_estimate": arv_estimate,
                "arv_source":   arv_source,
                "arv_spread":   spread,
            })

            if i % 5000 == 0:
                elapsed = time.time() - t_start
                logger.info(
                    "Progress: %d / %d (%.1f%%) — %.1fs elapsed | "
                    "COMP=%d JV_FALLBACK=%d",
                    i, total, i / total * 100, elapsed,
                    comp_count, fallback_count,
                )

    logger.info(
        "Metrics computed | total=%d | COMP=%d | JV_FALLBACK=%d | "
        "no_geom=%d | no_sqft=%d",
        total, comp_count, fallback_count, no_geom_count, no_sqft_count,
    )

    if dry_run:
        logger.info("[DRY-RUN] Sample of first 5 computed rows:")
        for row in computed[:5]:
            logger.info(
                "  %s / %-20s  arv=%s  source=%-12s  "
                "jv_psf=%s  spread=%s",
                row["county_fips"],
                row["parcel_id"],
                row["arv_estimate"],
                row["arv_source"],
                row["jv_per_sqft"],
                row["arv_spread"],
            )
        logger.info("[DRY-RUN] No data written to database.")
        return

    # ── Step 5 — Batch write ──────────────────────────────────────────── #
    update_sql = text("""
        UPDATE properties
        SET
            jv_per_sqft   = :jv_per_sqft,
            arv_estimate  = :arv_estimate,
            arv_source    = :arv_source,
            arv_spread    = :arv_spread,
            updated_at    = NOW()
        WHERE county_fips = :county_fips
          AND parcel_id   = :parcel_id
    """)

    total_batches = (len(computed) + batch_size - 1) // batch_size
    total_updated = 0

    logger.info(
        "Writing to database in %d batches of up to %d rows...",
        total_batches, batch_size,
    )

    for batch_num, batch in enumerate(_chunks(computed, batch_size), start=1):
        with engine.begin() as conn:
            conn.execute(update_sql, batch)
        total_updated += len(batch)

        if batch_num % 10 == 0 or batch_num == total_batches:
            elapsed = time.time() - t_start
            pct     = total_updated / len(computed) * 100
            logger.info(
                "Batch %d/%d — %d rows written (%.1f%%) — %.1fs elapsed",
                batch_num, total_batches, total_updated, pct, elapsed,
            )

    # ── Step 6 — Summary ─────────────────────────────────────────────── #
    elapsed = time.time() - t_start
    logger.info(
        "ARV calculation complete | processed=%d | updated=%d | "
        "COMP=%d | JV_FALLBACK=%d | no_geom=%d | no_sqft=%d | "
        "duration=%.1fs",
        len(computed), total_updated,
        comp_count, fallback_count,
        no_geom_count, no_sqft_count, elapsed,
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute and store ARV metrics for all eligible parcels.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Compute metrics but do not write to the database.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Recalculate all eligible parcels, even if arv_estimate is already set.",
    )
    parser.add_argument(
        "--batch-size", type=int, default=DEFAULT_BATCH,
        help=f"Rows per transaction batch (default: {DEFAULT_BATCH}).",
    )
    parser.add_argument(
        "--county", type=str, default=None,
        help="Restrict run to a single county_fips value (e.g. 12033).",
    )
    parser.add_argument(
        "--radius", type=float, default=DEFAULT_RADIUS_MILES,
        help=f"Comp search radius in miles (default: {DEFAULT_RADIUS_MILES}).",
    )
    parser.add_argument(
        "--min-comps", type=int, default=DEFAULT_MIN_COMPS,
        help=f"Minimum qualifying comps for COMP arv_source (default: {DEFAULT_MIN_COMPS}).",
    )
    parser.add_argument(
        "--year-tolerance", type=int, default=DEFAULT_YEAR_TOLERANCE,
        help=f"+/- years built tolerance for comp selection (default: {DEFAULT_YEAR_TOLERANCE}).",
    )
    parser.add_argument(
        "--rehab-cost", type=float, default=DEFAULT_REHAB_COST,
        help=f"Rehab cost per sqft for arv_spread (default: {DEFAULT_REHAB_COST}).",
    )
    args = parser.parse_args()

    run_arv_calculation(
        dry_run=args.dry_run,
        force=args.force,
        batch_size=args.batch_size,
        county=args.county,
        radius_miles=args.radius,
        min_comps=args.min_comps,
        year_tolerance=args.year_tolerance,
        rehab_cost=args.rehab_cost,
    )


if __name__ == "__main__":
    main()
