"""
Seed subscription_bundles and bundle_counties.
Also activates Santa Rosa County (12113).

Idempotent — safe to run multiple times.

Bundles seeded:
    pensacola_metro — Escambia (12033) + Santa Rosa (12113)

Usage:
    python scripts/seeds/seed_bundles.py
"""
import sys
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, ROOT)

from sqlalchemy import create_engine, text
from config.settings import settings

BUNDLES = [
    {
        "bundle_name": "pensacola_metro",
        "description": "Pensacola Metro area — Escambia and Santa Rosa counties",
        "is_active": True,
        "counties": ["12033", "12113"],
    },
]


def main() -> None:
    engine = create_engine(settings.sync_database_url, echo=False)

    with engine.begin() as conn:

        # Activate Santa Rosa County
        conn.execute(
            text("UPDATE counties SET active = TRUE WHERE county_fips = '12113'")
        )
        print("Santa Rosa County (12113) activated.")

        for bundle in BUNDLES:
            # Insert bundle — skip if already exists
            result = conn.execute(
                text("""
                    INSERT INTO subscription_bundles (bundle_name, description, is_active)
                    VALUES (:bundle_name, :description, :is_active)
                    ON CONFLICT (bundle_name) DO NOTHING
                """),
                {
                    "bundle_name": bundle["bundle_name"],
                    "description": bundle["description"],
                    "is_active":   bundle["is_active"],
                },
            )
            if result.rowcount == 1:
                print(f"Inserted bundle '{bundle['bundle_name']}'.")
            else:
                print(f"Bundle '{bundle['bundle_name']}' already exists — skipped.")

            # Fetch the bundle id
            row = conn.execute(
                text("SELECT id FROM subscription_bundles WHERE bundle_name = :name"),
                {"name": bundle["bundle_name"]},
            ).fetchone()
            bundle_id = row[0]

            # Insert bundle county members
            for fips in bundle["counties"]:
                r = conn.execute(
                    text("""
                        INSERT INTO bundle_counties (bundle_id, county_fips)
                        VALUES (:bundle_id, :county_fips)
                        ON CONFLICT (bundle_id, county_fips) DO NOTHING
                    """),
                    {"bundle_id": bundle_id, "county_fips": fips},
                )
                if r.rowcount == 1:
                    print(f"  Added county {fips} to bundle '{bundle['bundle_name']}'.")
                else:
                    print(f"  County {fips} already in bundle '{bundle['bundle_name']}' — skipped.")

    print("seed_bundles complete.")


if __name__ == "__main__":
    main()
