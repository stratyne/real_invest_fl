"""
scripts/validate_cama.py
--------------------------
Full dual-county CAMA validation report.
Covers Escambia (12033) and Santa Rosa (12113).

Checks:
    1.  Enrichment progress — both counties
    2.  CAMA field population rates — side-by-side parity
    3.  Field value sanity — year built, living area, zoning,
        exterior wall, foundation, roof — both counties
    4.  eff_yr_blt divergence (remodel indicator) — both counties
    5.  Sale history coverage — both counties
    6.  MM/YYYY normalized dates — both counties
    7.  Sale type breakdown — both counties
    8.  Arms-length price/sqft sanity — both counties
    9.  Source verification — both counties
    10. Parcels with anomalous data — both counties

Usage:
    python scripts/validate_cama.py

Output: plain-text report to stdout.
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import settings  # noqa: E402

engine = create_engine(settings.host_sync_database_url)

COUNTIES = {
    "12033": "Escambia",
    "12113": "Santa Rosa",
}

SEP  = "=" * 78
SEP2 = "-" * 78


def run_query(sql: str, params: dict | None = None) -> list[dict]:
    with engine.connect() as conn:
        result = conn.execute(text(sql), params or {})
        keys = list(result.keys())
        return [dict(zip(keys, row)) for row in result.fetchall()]


def pct(n: int | None, total: int | None) -> str:
    if not n or not total:
        return "—"
    return f"{n / total * 100:.1f}%"


def fmt(n: int | float | None) -> str:
    if n is None:
        return "—"
    if isinstance(n, float):
        return f"{n:,.2f}"
    return f"{n:,}"


def print_section(title: str) -> None:
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)


def print_sub(title: str) -> None:
    print(f"\n{SEP2}")
    print(f"  {title}")
    print(SEP2)


# ── 1. Enrichment Progress ────────────────────────────────────────────────────

def section_progress() -> None:
    print_section("1. ENRICHMENT PROGRESS")

    rows = run_query("""
        SELECT
            county_fips,
            COUNT(*)                                              AS total,
            COUNT(*) FILTER (WHERE cama_enriched_at IS NOT NULL) AS enriched,
            COUNT(*) FILTER (WHERE cama_enriched_at IS NULL)     AS remaining,
            MIN(cama_enriched_at)                                AS first_enriched,
            MAX(cama_enriched_at)                                AS last_enriched
        FROM properties
        WHERE dor_uc = '001'
          AND county_fips IN ('12033', '12113')
        GROUP BY county_fips
        ORDER BY county_fips
    """)

    print(f"\n{'County':<12} {'Total':>8} {'Enriched':>10} {'Remaining':>10} "
          f"{'Progress':>10}  {'First Enriched':<22} {'Last Enriched'}")
    print("-" * 78)
    for r in rows:
        name = COUNTIES[r["county_fips"]]
        print(
            f"{name:<12} {fmt(r['total']):>8} {fmt(r['enriched']):>10} "
            f"{fmt(r['remaining']):>10} {pct(r['enriched'], r['total']):>10}  "
            f"{str(r['first_enriched'])[:19]:<22} {str(r['last_enriched'])[:19]}"
        )


# ── 2. CAMA Field Population Rates ───────────────────────────────────────────

def section_field_rates() -> None:
    print_section("2. CAMA FIELD POPULATION RATES (enriched parcels only)")

    fields = [
        "exterior_wall",
        "roof_type",
        "foundation_type",
        "tot_lvg_area",
        "act_yr_blt",
        "eff_yr_blt",
        "zoning",
        "bedrooms",
        "bathrooms",
        "cama_quality_code",
        "cama_condition_code",
    ]

    select_parts = ["county_fips", "COUNT(*) AS total"]
    for col in fields:
        select_parts.append(
            f"COUNT({col}) FILTER (WHERE {col} IS NOT NULL) AS {col}"
        )

    rows = run_query(f"""
        SELECT {', '.join(select_parts)}
        FROM properties
        WHERE dor_uc = '001'
          AND cama_enriched_at IS NOT NULL
          AND county_fips IN ('12033', '12113')
        GROUP BY county_fips
        ORDER BY county_fips
    """)

    data = {r["county_fips"]: r for r in rows}
    esc = data.get("12033", {})
    sr  = data.get("12113", {})

    print(f"\n{'Field':<22} {'Escambia':>10} {'Esc%':>7} "
          f"{'Santa Rosa':>12} {'SR%':>7}  {'Match?'}")
    print("-" * 68)
    for col in fields:
        e_n = esc.get(col, 0)
        s_n = sr.get(col, 0)
        e_t = esc.get("total", 0)
        s_t = sr.get("total", 0)
        e_p = e_n / e_t * 100 if e_t else 0
        s_p = s_n / s_t * 100 if s_t else 0
        # Flag significant parity gap (>5 percentage points, both non-zero)
        gap = abs(e_p - s_p)
        flag = ""
        if e_p == 0 and s_p == 0:
            flag = "both absent"
        elif e_p == 0 and s_p > 0:
            flag = "⚠ ESC absent"
        elif gap > 5 and e_p > 0 and s_p > 0:
            flag = f"⚠ {gap:.0f}pp gap"
        print(
            f"{col:<22} {fmt(e_n):>10} {pct(e_n, e_t):>7} "
            f"{fmt(s_n):>12} {pct(s_n, s_t):>7}  {flag}"
        )
    print(f"\n{'TOTAL ENRICHED':<22} {fmt(esc.get('total',0)):>10} "
          f"{'':>7} {fmt(sr.get('total',0)):>12}")


# ── 3. Field Value Sanity ─────────────────────────────────────────────────────

def section_sanity() -> None:
    print_section("3. FIELD VALUE SANITY")

    # Year built distribution — both counties side by side
    print_sub("Year Built Distribution (act_yr_blt)")

    rows = run_query("""
        SELECT
            county_fips,
            CASE
                WHEN act_yr_blt IS NULL             THEN 'NULL'
                WHEN act_yr_blt < 1950              THEN 'pre-1950'
                WHEN act_yr_blt BETWEEN 1950 AND 1969 THEN '1950-1969'
                WHEN act_yr_blt BETWEEN 1970 AND 1989 THEN '1970-1989'
                WHEN act_yr_blt BETWEEN 1990 AND 2009 THEN '1990-2009'
                WHEN act_yr_blt >= 2010             THEN '2010+'
            END AS era,
            COUNT(*) AS cnt
        FROM properties
        WHERE dor_uc = '001'
          AND cama_enriched_at IS NOT NULL
          AND county_fips IN ('12033', '12113')
        GROUP BY county_fips, era
        ORDER BY era, county_fips
    """)

    era_data: dict[str, dict] = {}
    for r in rows:
        era_data.setdefault(r["era"], {})[r["county_fips"]] = r["cnt"]

    print(f"\n  {'Era':<15} {'Escambia':>10} {'Santa Rosa':>12}")
    print(f"  {'-'*40}")
    for era in ["pre-1950", "1950-1969", "1970-1989", "1990-2009", "2010+", "NULL"]:
        e = era_data.get(era, {})
        print(f"  {era:<15} {fmt(e.get('12033', 0)):>10} {fmt(e.get('12113', 0)):>12}")

    # Living area distribution
    print_sub("Living Area Distribution (tot_lvg_area)")

    rows = run_query("""
        SELECT
            county_fips,
            CASE
                WHEN tot_lvg_area IS NULL              THEN 'NULL'
                WHEN tot_lvg_area < 500                THEN '<500'
                WHEN tot_lvg_area BETWEEN 500  AND 999  THEN '500-999'
                WHEN tot_lvg_area BETWEEN 1000 AND 1499 THEN '1000-1499'
                WHEN tot_lvg_area BETWEEN 1500 AND 1999 THEN '1500-1999'
                WHEN tot_lvg_area BETWEEN 2000 AND 2999 THEN '2000-2999'
                WHEN tot_lvg_area BETWEEN 3000 AND 4999 THEN '3000-4999'
                WHEN tot_lvg_area >= 5000               THEN '5000+'
            END AS bucket,
            COUNT(*) AS cnt
        FROM properties
        WHERE dor_uc = '001'
          AND cama_enriched_at IS NOT NULL
          AND county_fips IN ('12033', '12113')
        GROUP BY county_fips, bucket
        ORDER BY bucket, county_fips
    """)

    bucket_data: dict[str, dict] = {}
    for r in rows:
        bucket_data.setdefault(r["bucket"], {})[r["county_fips"]] = r["cnt"]

    print(f"\n  {'SqFt Range':<15} {'Escambia':>10} {'Santa Rosa':>12}")
    print(f"  {'-'*40}")
    for b in ["<500", "500-999", "1000-1499", "1500-1999",
              "2000-2999", "3000-4999", "5000+", "NULL"]:
        d = bucket_data.get(b, {})
        print(f"  {b:<15} {fmt(d.get('12033', 0)):>10} {fmt(d.get('12113', 0)):>12}")

    # Avg / median living area
    rows = run_query("""
        SELECT
            county_fips,
            ROUND(AVG(tot_lvg_area), 0)                                AS avg_sqft,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY tot_lvg_area)  AS median_sqft,
            MIN(tot_lvg_area)                                          AS min_sqft,
            MAX(tot_lvg_area)                                          AS max_sqft
        FROM properties
        WHERE dor_uc = '001'
          AND cama_enriched_at IS NOT NULL
          AND tot_lvg_area IS NOT NULL
          AND county_fips IN ('12033', '12113')
        GROUP BY county_fips
        ORDER BY county_fips
    """)

    stats = {r["county_fips"]: r for r in rows}
    print(f"\n  {'Stat':<15} {'Escambia':>10} {'Santa Rosa':>12}")
    print(f"  {'-'*40}")
    for stat, key in [("Avg sqft", "avg_sqft"), ("Median sqft", "median_sqft"),
                      ("Min sqft", "min_sqft"), ("Max sqft", "max_sqft")]:
        e = stats.get("12033", {}).get(key)
        s = stats.get("12113", {}).get(key)
        print(f"  {stat:<15} {fmt(int(e) if e else 0):>10} "
              f"{fmt(int(s) if s else 0):>12}")

    # Top zoning codes — both counties
    print_sub("Top 10 Zoning Codes — Escambia")
    rows = run_query("""
        SELECT zoning, COUNT(*) AS cnt
        FROM properties
        WHERE county_fips = '12033' AND dor_uc = '001'
          AND cama_enriched_at IS NOT NULL AND zoning IS NOT NULL
        GROUP BY zoning ORDER BY cnt DESC LIMIT 10
    """)
    for r in rows:
        print(f"  {r['zoning']:<15} {fmt(r['cnt']):>8}")

    print_sub("Top 10 Zoning Codes — Santa Rosa")
    rows = run_query("""
        SELECT zoning, COUNT(*) AS cnt
        FROM properties
        WHERE county_fips = '12113' AND dor_uc = '001'
          AND cama_enriched_at IS NOT NULL AND zoning IS NOT NULL
        GROUP BY zoning ORDER BY cnt DESC LIMIT 10
    """)
    for r in rows:
        print(f"  {r['zoning']:<15} {fmt(r['cnt']):>8}")

    # Top exterior wall types — both counties
    print_sub("Top 10 Exterior Wall Types — Escambia")
    rows = run_query("""
        SELECT exterior_wall, COUNT(*) AS cnt
        FROM properties
        WHERE county_fips = '12033' AND dor_uc = '001'
          AND cama_enriched_at IS NOT NULL AND exterior_wall IS NOT NULL
        GROUP BY exterior_wall ORDER BY cnt DESC LIMIT 10
    """)
    for r in rows:
        print(f"  {r['exterior_wall']:<40} {fmt(r['cnt']):>6}")

    print_sub("Top 10 Exterior Wall Types — Santa Rosa")
    rows = run_query("""
        SELECT exterior_wall, COUNT(*) AS cnt
        FROM properties
        WHERE county_fips = '12113' AND dor_uc = '001'
          AND cama_enriched_at IS NOT NULL AND exterior_wall IS NOT NULL
        GROUP BY exterior_wall ORDER BY cnt DESC LIMIT 10
    """)
    for r in rows:
        print(f"  {r['exterior_wall']:<40} {fmt(r['cnt']):>6}")

    # Top foundation types — both counties
    print_sub("Top Foundation Types — Both Counties")
    rows = run_query("""
        SELECT
            county_fips,
            foundation_type,
            COUNT(*) AS cnt
        FROM properties
        WHERE dor_uc = '001'
          AND cama_enriched_at IS NOT NULL
          AND foundation_type IS NOT NULL
          AND county_fips IN ('12033', '12113')
        GROUP BY county_fips, foundation_type
        ORDER BY county_fips, cnt DESC
    """)

    print(f"\n  {'Foundation':<30} {'Escambia':>10} {'Santa Rosa':>12}")
    print(f"  {'-'*55}")
    found_data: dict[str, dict] = {}
    for r in rows:
        found_data.setdefault(r["foundation_type"], {})[r["county_fips"]] = r["cnt"]
    for ft, counts in sorted(found_data.items(),
                              key=lambda x: x[1].get("12033", 0), reverse=True)[:10]:
        print(f"  {ft:<30} {fmt(counts.get('12033', 0)):>10} "
              f"{fmt(counts.get('12113', 0)):>12}")


# ── 4. eff_yr_blt Divergence ──────────────────────────────────────────────────

def section_remodel() -> None:
    print_section("4. EFF_YR_BLT DIVERGENCE (remodel / renovation indicator)")

    rows = run_query("""
        SELECT
            county_fips,
            COUNT(*)                                                        AS enriched,
            COUNT(*) FILTER (WHERE eff_yr_blt IS NOT NULL
                               AND act_yr_blt IS NOT NULL
                               AND eff_yr_blt > act_yr_blt)                AS remodelled,
            COUNT(*) FILTER (WHERE eff_yr_blt IS NOT NULL
                               AND act_yr_blt IS NOT NULL
                               AND eff_yr_blt > act_yr_blt + 10)           AS major_remodel,
            ROUND(AVG(eff_yr_blt - act_yr_blt)
                  FILTER (WHERE eff_yr_blt > act_yr_blt), 1)               AS avg_gap_yrs
        FROM properties
        WHERE dor_uc = '001'
          AND cama_enriched_at IS NOT NULL
          AND county_fips IN ('12033', '12113')
        GROUP BY county_fips
        ORDER BY county_fips
    """)

    print(f"\n  {'County':<12} {'Enriched':>10} {'Remodelled':>12} "
          f"{'Remod%':>8} {'Major(>10yr)':>14} {'Avg Gap':>9}")
    print(f"  {'-'*68}")
    for r in rows:
        name = COUNTIES[r["county_fips"]]
        print(
            f"  {name:<12} {fmt(r['enriched']):>10} "
            f"{fmt(r['remodelled']):>12} "
            f"{pct(r['remodelled'], r['enriched']):>8} "
            f"{fmt(r['major_remodel']):>14} "
            f"{fmt(r['avg_gap_yrs']):>9} yrs"
        )


# ── 5 & 6. Sale History Coverage ─────────────────────────────────────────────

def section_sales() -> None:
    print_section("5. SALE HISTORY COVERAGE")

    print_sub("Overall Coverage")
    rows = run_query("""
        SELECT
            p.county_fips,
            COUNT(DISTINCT p.parcel_id)              AS enriched_parcels,
            COUNT(DISTINCT psh.parcel_id)            AS parcels_with_sales,
            COUNT(psh.id)                            AS total_sale_records,
            MIN(psh.sale_date)                       AS earliest_sale,
            MAX(psh.sale_date)                       AS latest_sale,
            ROUND(COUNT(psh.id)::numeric /
                  NULLIF(COUNT(DISTINCT psh.parcel_id), 0), 1)
                                                     AS avg_sales_per_parcel
        FROM properties p
        LEFT JOIN parcel_sale_history psh
               ON psh.county_fips = p.county_fips
              AND psh.parcel_id   = p.parcel_id
        WHERE p.dor_uc = '001'
          AND p.cama_enriched_at IS NOT NULL
          AND p.county_fips IN ('12033', '12113')
        GROUP BY p.county_fips
        ORDER BY p.county_fips
    """)

    print(f"\n  {'Metric':<28} {'Escambia':>14} {'Santa Rosa':>14}")
    print(f"  {'-'*58}")
    data = {r["county_fips"]: r for r in rows}
    esc = data.get("12033", {})
    sr  = data.get("12113", {})

    metrics = [
        ("Enriched parcels",       "enriched_parcels"),
        ("Parcels with sales",     "parcels_with_sales"),
        ("Total sale records",     "total_sale_records"),
        ("Avg sales / parcel",     "avg_sales_per_parcel"),
        ("Earliest sale",          "earliest_sale"),
        ("Latest sale",            "latest_sale"),
    ]
    for label, key in metrics:
        e_val = str(esc.get(key, "—"))[:14]
        s_val = str(sr.get(key, "—"))[:14]
        # Format numeric fields
        if key in ("enriched_parcels", "parcels_with_sales", "total_sale_records"):
            e_val = fmt(esc.get(key))
            s_val = fmt(sr.get(key))
        print(f"  {label:<28} {e_val:>14} {s_val:>14}")

    # Coverage pct row
    e_cov = pct(esc.get("parcels_with_sales"), esc.get("enriched_parcels"))
    s_cov = pct(sr.get("parcels_with_sales"),  sr.get("enriched_parcels"))
    print(f"  {'Coverage %':<28} {e_cov:>14} {s_cov:>14}")

    print_sub("MM/YYYY Normalized Dates (day=1)")
    rows = run_query("""
        SELECT
            county_fips,
            COUNT(*)                                         AS total_sales,
            COUNT(*) FILTER (WHERE EXTRACT(DAY FROM sale_date) = 1)
                                                             AS day_1_count
        FROM parcel_sale_history
        WHERE county_fips IN ('12033', '12113')
        GROUP BY county_fips
        ORDER BY county_fips
    """)
    print(f"\n  {'County':<12} {'Total Sales':>12} {'Day=1':>10} {'Day=1%':>8}")
    print(f"  {'-'*46}")
    for r in rows:
        print(
            f"  {COUNTIES[r['county_fips']]:<12} "
            f"{fmt(r['total_sales']):>12} "
            f"{fmt(r['day_1_count']):>10} "
            f"{pct(r['day_1_count'], r['total_sales']):>8}"
        )

    print_sub("Sales Per Parcel Distribution")
    rows = run_query("""
        SELECT
            sub.county_fips,
            CASE
                WHEN sale_count = 0 THEN '0 (no history)'
                WHEN sale_count = 1 THEN '1'
                WHEN sale_count BETWEEN 2 AND 3 THEN '2-3'
                WHEN sale_count BETWEEN 4 AND 6 THEN '4-6'
                WHEN sale_count >= 7             THEN '7+'
            END AS bucket,
            COUNT(*) AS parcels
        FROM (
            SELECT p.parcel_id, p.county_fips, COUNT(psh.id) AS sale_count
            FROM properties p
            LEFT JOIN parcel_sale_history psh
                   ON psh.county_fips = p.county_fips
                  AND psh.parcel_id   = p.parcel_id
            WHERE p.dor_uc = '001'
              AND p.cama_enriched_at IS NOT NULL
              AND p.county_fips IN ('12033', '12113')
            GROUP BY p.parcel_id, p.county_fips
        ) sub
        GROUP BY sub.county_fips, bucket
        ORDER BY bucket, sub.county_fips
    """)

    bucket_data: dict[str, dict] = {}
    for r in rows:
        bucket_data.setdefault(r["bucket"], {})[r["county_fips"]] = r["parcels"]

    print(f"\n  {'Bucket':<18} {'Escambia':>10} {'Santa Rosa':>12}")
    print(f"  {'-'*43}")
    for b in ["0 (no history)", "1", "2-3", "4-6", "7+"]:
        d = bucket_data.get(b, {})
        print(f"  {b:<18} {fmt(d.get('12033', 0)):>10} "
              f"{fmt(d.get('12113', 0)):>12}")

    print_sub("Sale Type Breakdown — Both Counties")
    rows = run_query("""
        SELECT
            county_fips,
            COALESCE(sale_type, 'NULL') AS sale_type,
            COUNT(*) AS cnt
        FROM parcel_sale_history
        WHERE county_fips IN ('12033', '12113')
        GROUP BY county_fips, sale_type
        ORDER BY county_fips, cnt DESC
    """)

    type_data: dict[str, dict] = {}
    for r in rows:
        type_data.setdefault(r["sale_type"], {})[r["county_fips"]] = r["cnt"]

    print(f"\n  {'Type':<10} {'Escambia':>10} {'Santa Rosa':>12}")
    print(f"  {'-'*35}")
    for st, counts in sorted(type_data.items(),
                              key=lambda x: x[1].get("12033", 0), reverse=True):
        print(f"  {st:<10} {fmt(counts.get('12033', 0)):>10} "
              f"{fmt(counts.get('12113', 0)):>12}")

    print_sub("Arms-Length WD Sales > $10,000 — Price/SqFt")
    rows = run_query("""
        SELECT
            psh.county_fips,
            COUNT(*)                                                        AS wd_sales,
            COUNT(*) FILTER (WHERE p.tot_lvg_area IS NOT NULL
                               AND p.tot_lvg_area > 0)                     AS with_ppsf,
            ROUND(AVG(psh.sale_price::numeric / p.tot_lvg_area)
                  FILTER (WHERE p.tot_lvg_area > 0), 2)                    AS avg_ppsf,
            ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (
                  ORDER BY psh.sale_price::numeric / p.tot_lvg_area)
                  FILTER (WHERE p.tot_lvg_area > 0)::numeric, 2)           AS median_ppsf,
            ROUND(MIN(psh.sale_price::numeric / p.tot_lvg_area)
                  FILTER (WHERE p.tot_lvg_area > 0), 2)                    AS min_ppsf,
            ROUND(MAX(psh.sale_price::numeric / p.tot_lvg_area)
                  FILTER (WHERE p.tot_lvg_area > 0), 2)                    AS max_ppsf
        FROM parcel_sale_history psh
        JOIN properties p
          ON p.county_fips = psh.county_fips
         AND p.parcel_id   = psh.parcel_id
        WHERE psh.county_fips IN ('12033', '12113')
          AND psh.sale_type  = 'WD'
          AND psh.sale_price > 10000
          AND p.dor_uc = '001'
          AND p.cama_enriched_at IS NOT NULL
        GROUP BY psh.county_fips
        ORDER BY psh.county_fips
    """)
    ppsf = {r["county_fips"]: r for r in rows}
    esc_p = ppsf.get("12033", {})
    sr_p  = ppsf.get("12113", {})

    print(f"\n  {'Metric':<20} {'Escambia':>12} {'Santa Rosa':>14}")
    print(f"  {'-'*50}")
    for label, key in [
        ("WD sales > $10k",  "wd_sales"),
        ("With price/sqft",  "with_ppsf"),
        ("Avg $/sqft",       "avg_ppsf"),
        ("Median $/sqft",    "median_ppsf"),
        ("Min $/sqft",       "min_ppsf"),
        ("Max $/sqft",       "max_ppsf"),
    ]:
        e_v = fmt(esc_p.get(key))
        s_v = fmt(sr_p.get(key))
        print(f"  {label:<20} {e_v:>12} {s_v:>14}")


# ── 6. Suspicious Value Flags ─────────────────────────────────────────────────

def section_flags() -> None:
    print_section("6. SUSPICIOUS VALUE FLAGS")

    rows = run_query("""
        SELECT
            p.county_fips,
            COUNT(*) FILTER (WHERE tot_lvg_area IS NOT NULL
                               AND tot_lvg_area < 100)          AS tiny_area,
            COUNT(*) FILTER (WHERE act_yr_blt IS NOT NULL
                               AND act_yr_blt > 2026)           AS future_yr_blt,
            COUNT(*) FILTER (WHERE act_yr_blt IS NOT NULL
                               AND act_yr_blt < 1800)           AS ancient_yr_blt,
            COUNT(*) FILTER (WHERE sale_price IS NOT NULL
                               AND sale_price > 0
                               AND sale_price < 500
                               AND sale_type = 'WD')            AS suspicious_wd_price
        FROM properties p
        LEFT JOIN parcel_sale_history psh
               ON psh.county_fips = p.county_fips
              AND psh.parcel_id   = p.parcel_id
        WHERE p.dor_uc = '001'
          AND p.cama_enriched_at IS NOT NULL
          AND p.county_fips IN ('12033', '12113')
        GROUP BY p.county_fips
        ORDER BY p.county_fips
    """)

    print(f"\n  {'Flag':<35} {'Escambia':>10} {'Santa Rosa':>12}")
    print(f"  {'-'*60}")
    data = {r["county_fips"]: r for r in rows}
    for label, key in [
        ("tot_lvg_area < 100 sqft",        "tiny_area"),
        ("act_yr_blt > 2026 (future)",     "future_yr_blt"),
        ("act_yr_blt < 1800 (ancient)",    "ancient_yr_blt"),
        ("WD sale price $1-$499",          "suspicious_wd_price"),
    ]:
        e = data.get("12033", {}).get(key, 0)
        s = data.get("12113", {}).get(key, 0)
        print(f"  {label:<35} {fmt(e):>10} {fmt(s):>12}")


# ── 7. Source Verification ────────────────────────────────────────────────────

def section_source() -> None:
    print_section("7. SOURCE VERIFICATION")

    print_sub("parcel_sale_history — source tag")
    rows = run_query("""
        SELECT
            county_fips,
            source,
            COUNT(*) AS cnt
        FROM parcel_sale_history
        WHERE county_fips IN ('12033', '12113')
        GROUP BY county_fips, source
        ORDER BY county_fips, cnt DESC
    """)
    print(f"\n  {'County':<12} {'Source':<30} {'Records':>10}")
    print(f"  {'-'*55}")
    for r in rows:
        print(f"  {COUNTIES[r['county_fips']]:<12} {r['source']:<30} "
              f"{fmt(r['cnt']):>10}")

    print_sub("properties — raw_cama_json population")
    rows = run_query("""
        SELECT
            county_fips,
            COUNT(*)                                              AS total,
            COUNT(*) FILTER (WHERE raw_cama_json IS NOT NULL)    AS with_json,
            COUNT(*) FILTER (WHERE raw_cama_json = '{}'::jsonb)  AS empty_json
        FROM properties
        WHERE dor_uc = '001'
          AND cama_enriched_at IS NOT NULL
          AND county_fips IN ('12033', '12113')
        GROUP BY county_fips
        ORDER BY county_fips
    """)
    print(f"\n  {'County':<12} {'Total':>8} {'With JSON':>10} "
          f"{'Empty {{}}':>10} {'JSON%':>7}")
    print(f"  {'-'*52}")
    for r in rows:
        print(
            f"  {COUNTIES[r['county_fips']]:<12} {fmt(r['total']):>8} "
            f"{fmt(r['with_json']):>10} {fmt(r['empty_json']):>10} "
            f"{pct(r['with_json'], r['total']):>7}"
        )


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(SEP)
    print("  PROJECT PENSTOCK — DUAL-COUNTY CAMA VALIDATION REPORT")
    print("  Counties: Escambia (12033) + Santa Rosa (12113)  |  dor_uc = '001'")
    print(SEP)

    section_progress()
    section_field_rates()
    section_sanity()
    section_remodel()
    section_sales()
    section_flags()
    section_source()

    print(f"\n{SEP}")
    print("  END OF REPORT")
    print(SEP)
