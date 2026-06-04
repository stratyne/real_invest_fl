#!/usr/bin/env python3
"""
enrich_missing_spatial_attrs.py

Derives missing phy_city and phy_zipcd for properties using PostGIS spatial
joins against Census TIGER reference tables (tiger_places, tiger_zcta).

Pass 1: ST_Within spatial join for all parcels with geometry.
Pass 2: Street-name neighbor inference for parcels without geometry.

Usage:
    python scripts/enrich_missing_spatial_attrs.py --county-fips 12113
    python scripts/enrich_missing_spatial_attrs.py --county-fips 12113 --dry-run
    python scripts/enrich_missing_spatial_attrs.py --county-fips 12113 --dor-uc 001

Non-negotiable behaviors:
    - Never overwrites a populated value.
    - All DB writes use text() via sync session.
    - Logs all outcomes - updated, unresolved, and inference failures.

Uses sync DB session (settings.host_sync_database_url) per project convention
for host-side scripts.
"""

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import settings


# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

def preflight_check(conn, county_fips: str) -> None:
    """Abort if TIGER reference tables are empty or county has no parcels."""
    zcta_count = conn.execute(
        text("SELECT COUNT(*) FROM tiger_zcta")
    ).scalar()
    places_count = conn.execute(
        text("SELECT COUNT(*) FROM tiger_places")
    ).scalar()

    if zcta_count == 0 or places_count == 0:
        print(
            "[error] TIGER reference tables are empty. "
            "Run scripts/load_tiger_reference.py first."
        )
        sys.exit(1)

    parcel_count = conn.execute(
        text(
            "SELECT COUNT(*) FROM properties "
            "WHERE county_fips = :fips"
        ),
        {"fips": county_fips},
    ).scalar()

    if parcel_count == 0:
        print(f"[error] No parcels found for county_fips={county_fips}.")
        sys.exit(1)

    print(f"[preflight] tiger_zcta: {zcta_count:,} rows")
    print(f"[preflight] tiger_places: {places_count:,} rows")
    print(f"[preflight] Properties in county {county_fips}: {parcel_count:,}")


# ---------------------------------------------------------------------------
# Baseline counts
# ---------------------------------------------------------------------------

def get_baseline(conn, county_fips: str, dor_uc: str | None) -> dict:
    dor_clause = "AND dor_uc = :dor_uc" if dor_uc else ""
    params = {"fips": county_fips}
    if dor_uc:
        params["dor_uc"] = dor_uc

    row = conn.execute(
        text(f"""
            SELECT
                COUNT(*) FILTER (
                    WHERE (phy_city IS NULL OR phy_city = '')
                    AND geom IS NOT NULL
                ) AS missing_city_has_geom,
                COUNT(*) FILTER (
                    WHERE (phy_zipcd IS NULL OR phy_zipcd = '')
                    AND geom IS NOT NULL
                ) AS missing_zip_has_geom,
                COUNT(*) FILTER (
                    WHERE (phy_city IS NULL OR phy_city = '')
                    AND geom IS NULL
                ) AS missing_city_no_geom,
                COUNT(*) FILTER (
                    WHERE (phy_zipcd IS NULL OR phy_zipcd = '')
                    AND geom IS NULL
                ) AS missing_zip_no_geom
            FROM properties
            WHERE county_fips = :fips
            {dor_clause}
        """),
        params,
    ).fetchone()

    return {
        "missing_city_has_geom":  row.missing_city_has_geom,
        "missing_zip_has_geom":   row.missing_zip_has_geom,
        "missing_city_no_geom":   row.missing_city_no_geom,
        "missing_zip_no_geom":    row.missing_zip_no_geom,
    }


# ---------------------------------------------------------------------------
# Pass 1 - Spatial join
# ---------------------------------------------------------------------------

def pass1_city(conn, county_fips: str, dor_uc: str | None, dry_run: bool) -> int:
    """Derive phy_city via ST_Within against tiger_places."""
    dor_clause = "AND p.dor_uc = :dor_uc" if dor_uc else ""
    params = {"fips": county_fips}
    if dor_uc:
        params["dor_uc"] = dor_uc

    # Identify affected parcel_ids and derived city values
    rows = conn.execute(
        text(f"""
            SELECT DISTINCT ON (p.parcel_id) p.parcel_id, UPPER(pl.name) AS city
            FROM properties p
            JOIN tiger_places pl
              ON ST_Within(p.geom, pl.geometry)
            WHERE p.county_fips = :fips
              AND (p.phy_city IS NULL OR p.phy_city = '')
              AND p.geom IS NOT NULL
              AND pl.statefp = '12'
            {dor_clause}
            ORDER BY p.parcel_id, ST_Area(pl.geometry) DESC
        """),
        params,
    ).fetchall()

    if not rows:
        print("[pass1] city: no parcels resolved via spatial join.")
        return 0

    if dry_run:
        print(f"[pass1] city: {len(rows):,} parcels would be updated (dry run).")
        for r in rows[:5]:
            print(f"  {r.parcel_id} -> {r.city}")
        if len(rows) > 5:
            print(f"  ... and {len(rows) - 5} more")
        return len(rows)

    # Batch update
    conn.execute(
        text(f"""
            UPDATE properties p
            SET phy_city = derived.city
            FROM (
                SELECT DISTINCT ON (p2.parcel_id) p2.parcel_id, UPPER(pl.name) AS city
                FROM properties p2
                JOIN tiger_places pl
                ON ST_Within(p2.geom, pl.geometry)
                WHERE p2.county_fips = :fips
                AND (p2.phy_city IS NULL OR p2.phy_city = '')
                AND p2.geom IS NOT NULL
                AND pl.statefp = '12'
                {dor_clause}
                ORDER BY p2.parcel_id, ST_Area(pl.geometry) DESC
            ) AS derived
            WHERE p.parcel_id = derived.parcel_id
              AND p.county_fips = :fips
        """),
        params,
    )
    print(f"[pass1] city: {len(rows):,} parcels updated.")
    return len(rows)


def pass1_zip(conn, county_fips: str, dor_uc: str | None, dry_run: bool) -> int:
    """Derive phy_zipcd via ST_Within against tiger_zcta."""
    dor_clause = "AND p.dor_uc = :dor_uc" if dor_uc else ""
    params = {"fips": county_fips}
    if dor_uc:
        params["dor_uc"] = dor_uc

    rows = conn.execute(
        text(f"""
            SELECT p.parcel_id, z.zcta5 AS derived_zip
            FROM properties p
            JOIN tiger_zcta z
              ON ST_Within(p.geom, z.geometry)
            WHERE p.county_fips = :fips
              AND (p.phy_zipcd IS NULL OR p.phy_zipcd = '')
              AND p.geom IS NOT NULL
            {dor_clause}
        """),
        params,
    ).fetchall()

    if not rows:
        print("[pass1] zip: no parcels resolved via spatial join.")
        return 0

    if dry_run:
        print(f"[pass1] zip: {len(rows):,} parcels would be updated (dry run).")
        for r in rows[:5]:
            print(f"  {r.parcel_id} -> {r.derived_zip}")
        if len(rows) > 5:
            print(f"  ... and {len(rows) - 5} more")
        return len(rows)

    conn.execute(
        text(f"""
            UPDATE properties p
            SET phy_zipcd = derived.zip
            FROM (
                SELECT p2.parcel_id, z.zcta5 AS zip
                FROM properties p2
                JOIN tiger_zcta z
                  ON ST_Within(p2.geom, z.geometry)
                WHERE p2.county_fips = :fips
                  AND (p2.phy_zipcd IS NULL OR p2.phy_zipcd = '')
                  AND p2.geom IS NOT NULL
                {dor_clause}
            ) AS derived
            WHERE p.parcel_id = derived.parcel_id
              AND p.county_fips = :fips
        """),
        params,
    )
    print(f"[pass1] zip: {len(rows):,} parcels updated.")
    return len(rows)


def pass1_city_nearest(conn, county_fips: str, dor_uc: str | None, dry_run: bool) -> int:
    """
    For parcels with geometry that ST_Within could not resolve (unincorporated
    land outside all Census place polygons), assign city from the nearest
    tiger_places polygon using ST_Distance. Applies only to parcels still
    missing phy_city after pass1_city.
    """
    dor_clause_p  = "AND p.dor_uc = :dor_uc"  if dor_uc else ""
    dor_clause_p2 = "AND p2.dor_uc = :dor_uc" if dor_uc else ""
    params = {"fips": county_fips}
    if dor_uc:
        params["dor_uc"] = dor_uc

    rows = conn.execute(
        text(f"""
            SELECT DISTINCT ON (p.parcel_id)
                p.parcel_id,
                UPPER(pl.name) AS city,
                ST_Distance(p.geom::geography, pl.geometry::geography) AS dist_m
            FROM properties p
            CROSS JOIN LATERAL (
                SELECT name, geometry
                FROM tiger_places
                WHERE statefp = '12'
                ORDER BY p.geom <-> geometry
                LIMIT 1
            ) pl
            WHERE p.county_fips = :fips
              AND (p.phy_city IS NULL OR p.phy_city = '')
              AND p.geom IS NOT NULL
            {dor_clause_p}
            ORDER BY p.parcel_id, dist_m
        """),
        params,
    ).fetchall()

    if not rows:
        print("[pass1_nearest] city: no parcels resolved.")
        return 0

    if dry_run:
        print(f"[pass1_nearest] city: {len(rows):,} parcels would be updated (dry run).")
        for r in rows[:10]:
            print(f"  {r.parcel_id} -> {r.city} ({r.dist_m:.0f}m)")
        if len(rows) > 10:
            print(f"  ... and {len(rows) - 10} more")
        return len(rows)

    conn.execute(
        text(f"""
            UPDATE properties p
            SET phy_city = derived.city
            FROM (
                SELECT DISTINCT ON (p2.parcel_id)
                    p2.parcel_id,
                    UPPER(pl.name) AS city
                FROM properties p2
                CROSS JOIN LATERAL (
                    SELECT name, geometry
                    FROM tiger_places
                    WHERE statefp = '12'
                    ORDER BY p2.geom <-> geometry
                    LIMIT 1
                ) pl
                WHERE p2.county_fips = :fips
                  AND (p2.phy_city IS NULL OR p2.phy_city = '')
                  AND p2.geom IS NOT NULL
                {dor_clause_p2}
                ORDER BY p2.parcel_id
            ) AS derived
            WHERE p.parcel_id = derived.parcel_id
              AND p.county_fips = :fips
              AND (p.phy_city IS NULL OR p.phy_city = '')
        """),
        params,
    )
    print(f"[pass1_nearest] city: {len(rows):,} parcels updated.")
    return len(rows)


# ---------------------------------------------------------------------------
# Pass 2 - Neighbor inference (no-geometry parcels)
# ---------------------------------------------------------------------------

def _strip_house_number(addr: str) -> str:
    """Return street name portion only - strip leading house number."""
    return re.sub(r"^\d+\s*", "", addr).strip().upper()


def pass2(conn, county_fips: str, dor_uc: str | None, dry_run: bool) -> dict:
    """
    For parcels without geometry, infer phy_city and phy_zipcd from
    neighbors sharing the same street name within the same county.
    Applies only if >= 80% of geometry-bearing neighbors on the street agree.
    """
    dor_clause = "AND dor_uc = :dor_uc" if dor_uc else ""
    params = {"fips": county_fips}
    if dor_uc:
        params["dor_uc"] = dor_uc

    # Fetch no-geometry parcels missing city or zip
    no_geom_rows = conn.execute(
        text(f"""
            SELECT
                parcel_id,
                phy_addr1,
                phy_city,
                phy_zipcd
            FROM properties
            WHERE county_fips = :fips
              AND geom IS NULL
              AND (
                  (phy_city IS NULL OR phy_city = '')
                  OR (phy_zipcd IS NULL OR phy_zipcd = '')
              )
            {dor_clause}
        """),
        params,
    ).fetchall()

    if not no_geom_rows:
        print("[pass2] No no-geometry parcels require inference.")
        return {"city_updated": 0, "zip_updated": 0, "unresolved": 0}

    # Fetch all geometry-bearing parcels on this county with city+zip populated
    neighbor_rows = conn.execute(
        text("""
            SELECT phy_addr1, phy_city, phy_zipcd
            FROM properties
            WHERE county_fips = :fips
              AND geom IS NOT NULL
              AND phy_addr1 IS NOT NULL
              AND phy_addr1 != ''
        """),
        {"fips": county_fips},
    ).fetchall()

    # Build street-level lookup: street_name -> Counter of (city, zip)
    street_city: dict[str, Counter] = {}
    street_zip: dict[str, Counter] = {}

    for n in neighbor_rows:
        if not n.phy_addr1:
            continue
        street = _strip_house_number(n.phy_addr1)
        if n.phy_city:
            street_city.setdefault(street, Counter())[n.phy_city] += 1
        if n.phy_zipcd:
            street_zip.setdefault(street, Counter())[n.phy_zipcd] += 1

    THRESHOLD = 0.80
    city_updated = 0
    zip_updated = 0
    unresolved = []

    for row in no_geom_rows:
        if not row.phy_addr1:
            unresolved.append((row.parcel_id, "no phy_addr1"))
            continue

        street = _strip_house_number(row.phy_addr1)
        needs_city = not row.phy_city
        needs_zip = not row.phy_zipcd
        inferred_city = None
        inferred_zip = None

        if needs_city and street in street_city:
            counter = street_city[street]
            total = sum(counter.values())
            top_city, top_count = counter.most_common(1)[0]
            if top_count / total >= THRESHOLD:
                inferred_city = top_city
            else:
                unresolved.append(
                    (row.parcel_id, f"city threshold not met on street '{street}'")
                )

        if needs_zip and street in street_zip:
            counter = street_zip[street]
            total = sum(counter.values())
            top_zip, top_count = counter.most_common(1)[0]
            if top_count / total >= THRESHOLD:
                inferred_zip = top_zip
            else:
                unresolved.append(
                    (row.parcel_id, f"zip threshold not met on street '{street}'")
                )

        if needs_city and not inferred_city and street not in street_city:
            unresolved.append(
                (row.parcel_id, f"city: no neighbors found on street '{street}'")
            )
        if needs_zip and not inferred_zip and street not in street_zip:
            unresolved.append(
                (row.parcel_id, f"zip: no neighbors found on street '{street}'")
            )

        if dry_run:
            if inferred_city:
                print(
                    f"  [dry run] {row.parcel_id} city -> {inferred_city}"
                )
                city_updated += 1
            if inferred_zip:
                print(
                    f"  [dry run] {row.parcel_id} zip  -> {inferred_zip}"
                )
                zip_updated += 1
            continue

        if inferred_city:
            conn.execute(
                text("""
                    UPDATE properties
                    SET phy_city = :city
                    WHERE parcel_id = :parcel_id
                      AND county_fips = :fips
                      AND (phy_city IS NULL OR phy_city = '')
                """),
                {"city": inferred_city, "parcel_id": row.parcel_id, "fips": county_fips},
            )
            city_updated += 1

        if inferred_zip:
            conn.execute(
                text("""
                    UPDATE properties
                    SET phy_zipcd = :zip
                    WHERE parcel_id = :parcel_id
                      AND county_fips = :fips
                      AND (phy_zipcd IS NULL OR phy_zipcd = '')
                """),
                {"zip": inferred_zip, "parcel_id": row.parcel_id, "fips": county_fips},
            )
            zip_updated += 1

    print(f"[pass2] city inferred: {city_updated}")
    print(f"[pass2] zip  inferred: {zip_updated}")
    print(f"[pass2] unresolved:    {len(unresolved)}")

    if unresolved:
        print("[pass2] Unresolved parcels:")
        for parcel_id, reason in unresolved:
            print(f"  {parcel_id}: {reason}")

    return {
        "city_updated": city_updated,
        "zip_updated": zip_updated,
        "unresolved": len(unresolved),
    }


# ---------------------------------------------------------------------------
# Final counts
# ---------------------------------------------------------------------------

def get_remaining(conn, county_fips: str, dor_uc: str | None) -> dict:
    return get_baseline(conn, county_fips, dor_uc)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enrich missing phy_city and phy_zipcd via spatial join."
    )
    parser.add_argument(
        "--county-fips",
        required=True,
        help="County FIPS code to process (e.g. 12113)",
    )
    parser.add_argument(
        "--dor-uc",
        default=None,
        help="Optional DOR use code filter (e.g. 001 for SFR only).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log what would be updated without writing to DB.",
    )
    args = parser.parse_args()

    engine = create_engine(settings.host_sync_database_url)

    with engine.begin() as conn:
        preflight_check(conn, args.county_fips)

        print(f"\n[baseline] County {args.county_fips}")
        baseline = get_baseline(conn, args.county_fips, args.dor_uc)
        print(f"  missing city  (has geom):  {baseline['missing_city_has_geom']:,}")
        print(f"  missing zip   (has geom):  {baseline['missing_zip_has_geom']:,}")
        print(f"  missing city  (no geom):   {baseline['missing_city_no_geom']:,}")
        print(f"  missing zip   (no geom):   {baseline['missing_zip_no_geom']:,}")

        if args.dry_run:
            print("\n[mode] DRY RUN - no writes will be committed.\n")

        print("\n--- Pass 1: Spatial join ---")
        p1_city         = pass1_city(conn, args.county_fips, args.dor_uc, args.dry_run)
        p1_zip          = pass1_zip(conn, args.county_fips, args.dor_uc, args.dry_run)
        p1_city_nearest = pass1_city_nearest(conn, args.county_fips, args.dor_uc, args.dry_run)

        print("\n--- Pass 2: Neighbor inference ---")
        p2 = pass2(conn, args.county_fips, args.dor_uc, args.dry_run)

        if not args.dry_run:
            print(f"\n[remaining] County {args.county_fips}")
            remaining = get_remaining(conn, args.county_fips, args.dor_uc)
            print(f"  missing city  (has geom):  {remaining['missing_city_has_geom']:,}")
            print(f"  missing zip   (has geom):  {remaining['missing_zip_has_geom']:,}")
            print(f"  missing city  (no geom):   {remaining['missing_city_no_geom']:,}")
            print(f"  missing zip   (no geom):   {remaining['missing_zip_no_geom']:,}")

        print("\n[summary]")
        print(f"  Pass 1 city updated:      {p1_city:,}")
        print(f"  Pass 1 city nearest:      {p1_city_nearest:,}")
        print(f"  Pass 1 zip  updated:      {p1_zip:,}")
        print(f"  Pass 2 city inferred:     {p2['city_updated']:,}")
        print(f"  Pass 2 zip  inferred:     {p2['zip_updated']:,}")
        print(f"  Pass 2 unresolved:        {p2['unresolved']:,}")

    if args.dry_run:
        print("\n[done] Dry run complete. No changes written.")
    else:
        print("\n[done] Enrichment complete.")


if __name__ == "__main__":
    main()
