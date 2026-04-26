"""
Seed the filter_profiles table with the Escambia POC filter profile.
Reads config/filter_profiles/escambia_poc.json as the filter_criteria source.
Safe to run multiple times — uses INSERT ... ON CONFLICT (profile_name) DO NOTHING.

Usage:
    python -m scripts.seeds.seed_filter_profile
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import json
from sqlalchemy import create_engine, text
from config.settings import settings

COUNTY_FIPS      = "12033"   # Escambia
PROFILE_NAME     = "escambia_poc"
CONFIG_FILE_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', 'config', 'filter_profiles', 'escambia_poc.json'
)


def main() -> None:
    # ------------------------------------------------------------------ #
    # Load filter criteria from JSON                                       #
    # ------------------------------------------------------------------ #
    config_path = os.path.abspath(CONFIG_FILE_PATH)
    print(f"Reading filter profile: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        filter_criteria = json.load(f)

    print(f"Filter criteria loaded. Version: {filter_criteria.get('version')}, "
          f"Logic: {filter_criteria.get('logic')}, "
          f"Dimensions: {len(filter_criteria.get('filters', {}))}")

    # ------------------------------------------------------------------ #
    # Insert                                                               #
    # ------------------------------------------------------------------ #
    engine = create_engine(settings.sync_database_url, echo=False)

    insert_sql = text("""
        INSERT INTO filter_profiles (
            profile_name,
            county_fips,
            description,
            is_active,
            version,
            filter_criteria,
            rehab_cost_per_sqft,
            min_comp_sales_for_arv,
            comp_radius_miles,
            comp_year_built_tolerance,
            listing_type_priority,
            deal_score_weights,
            allow_automated_outreach,
            max_outreach_attempts
        )
        VALUES (
            :profile_name,
            :county_fips,
            :description,
            :is_active,
            :version,
            :filter_criteria,
            :rehab_cost_per_sqft,
            :min_comp_sales_for_arv,
            :comp_radius_miles,
            :comp_year_built_tolerance,
            :listing_type_priority,
            :deal_score_weights,
            :allow_automated_outreach,
            :max_outreach_attempts
        )
        ON CONFLICT (profile_name) DO NOTHING
    """)

    row = {
        "profile_name":             PROFILE_NAME,
        "county_fips":              COUNTY_FIPS,
        "description":              (
            "Escambia County proof-of-concept filter profile. "
            "3/2 SFR, built 1950+, IMP_QUAL 2-4, 800-3000 sqft, "
            "JV $50k-$350k, list price max $225k."
        ),
        "is_active":                True,
        "version":                  filter_criteria.get("version", 1),
        "filter_criteria":          json.dumps(filter_criteria),
        "rehab_cost_per_sqft":      22.00,
        "min_comp_sales_for_arv":   3,
        "comp_radius_miles":        0.5,
        "comp_year_built_tolerance": 15,
        "listing_type_priority":    json.dumps({}),
        "deal_score_weights":       json.dumps({}),
        "allow_automated_outreach": False,
        "max_outreach_attempts":    3,
    }

    with engine.begin() as conn:
        result = conn.execute(insert_sql, row)
        if result.rowcount == 1:
            print(f"Inserted filter profile '{PROFILE_NAME}'.")
        else:
            print(f"Filter profile '{PROFILE_NAME}' already exists — skipped.")


if __name__ == "__main__":
    main()
