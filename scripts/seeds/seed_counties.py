"""
Seed the counties table with all 67 Florida counties.
Safe to run multiple times — uses INSERT ... ON CONFLICT DO NOTHING.

Usage:
    python -m seeds.seed_counties
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import create_engine, text
from config.settings import settings

FL_COUNTIES = [
    ("12001", 11, "Alachua"),
    ("12003", 12, "Baker"),
    ("12005", 13, "Bay"),
    ("12007", 14, "Bradford"),
    ("12009", 15, "Brevard"),
    ("12011", 16, "Broward"),
    ("12013", 17, "Calhoun"),
    ("12015", 18, "Charlotte"),
    ("12017", 19, "Citrus"),
    ("12019", 20, "Clay"),
    ("12021", 21, "Collier"),
    ("12023", 22, "Columbia"),
    ("12086", 23, "Miami-Dade"),
    ("12027", 24, "DeSoto"),
    ("12029", 25, "Dixie"),
    ("12031", 26, "Duval"),
    ("12033", 27, "Escambia"),
    ("12035", 28, "Flagler"),
    ("12037", 29, "Franklin"),
    ("12039", 30, "Gadsden"),
    ("12041", 31, "Gilchrist"),
    ("12043", 32, "Glades"),
    ("12045", 33, "Gulf"),
    ("12047", 34, "Hamilton"),
    ("12049", 35, "Hardee"),
    ("12051", 36, "Hendry"),
    ("12053", 37, "Hernando"),
    ("12055", 38, "Highlands"),
    ("12057", 39, "Hillsborough"),
    ("12059", 40, "Holmes"),
    ("12061", 41, "Indian River"),
    ("12063", 42, "Jackson"),
    ("12065", 43, "Jefferson"),
    ("12067", 44, "Lafayette"),
    ("12069", 45, "Lake"),
    ("12071", 46, "Lee"),
    ("12073", 47, "Leon"),
    ("12075", 48, "Levy"),
    ("12077", 49, "Liberty"),
    ("12079", 50, "Madison"),
    ("12081", 51, "Manatee"),
    ("12083", 52, "Marion"),
    ("12085", 53, "Martin"),
    ("12087", 54, "Monroe"),
    ("12089", 55, "Nassau"),
    ("12091", 56, "Okaloosa"),
    ("12093", 57, "Okeechobee"),
    ("12095", 58, "Orange"),
    ("12097", 59, "Osceola"),
    ("12099", 60, "Palm Beach"),
    ("12101", 61, "Pasco"),
    ("12103", 62, "Pinellas"),
    ("12105", 63, "Polk"),
    ("12107", 64, "Putnam"),
    ("12109", 65, "Saint Johns"),
    ("12111", 66, "Saint Lucie"),
    ("12113", 67, "Santa Rosa"),
    ("12115", 68, "Sarasota"),
    ("12117", 69, "Seminole"),
    ("12119", 70, "Sumter"),
    ("12121", 71, "Suwannee"),
    ("12123", 72, "Taylor"),
    ("12125", 73, "Union"),
    ("12127", 74, "Volusia"),
    ("12129", 75, "Wakulla"),
    ("12131", 76, "Walton"),
    ("12133", 77, "Washington"),
]

POC_COUNTY_FIPS = "12033"  # Escambia


def main() -> None:
    engine = create_engine(settings.sync_database_url, echo=False)

    insert_sql = text("""
        INSERT INTO counties (
            county_fips, dor_county_no, county_name,
            state_abbr, active, poc_county
        )
        VALUES (
            :county_fips, :dor_county_no, :county_name,
            'FL', :active, :poc_county
        )
        ON CONFLICT (county_fips) DO NOTHING
    """)

    rows = [
        {
            "county_fips":   fips,
            "dor_county_no": dor_no,
            "county_name":   name,
            "active":        fips == POC_COUNTY_FIPS,
            "poc_county":    fips == POC_COUNTY_FIPS,
        }
        for fips, dor_no, name in FL_COUNTIES
    ]

    with engine.begin() as conn:
        result = conn.execute(insert_sql, rows)
        print(f"Inserted {result.rowcount} counties.")


if __name__ == "__main__":
    main()
