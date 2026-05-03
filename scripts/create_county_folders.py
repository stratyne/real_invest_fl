# scripts/create_county_folders.py
"""
Creates the canonical data/raw/counties folder tree for all 67 Florida counties
and the _unsorted holding folder.

Safe to run multiple times — exist_ok=True means no errors if folders already exist.

Usage:
    python scripts/create_county_folders.py

Run this once from the project root before moving any existing data files.
The folder key format is:  {county_fips}_{county_name_snake}
e.g.  12033_escambia,  12113_santa_rosa,  12086_miami_dade

Subfolders created per county:
    nal/          — extracted NAL CSV file(s)
    sdf/          — extracted SDF CSV file(s)
    gis/          — extracted shapefile folder(s)
    nav/          — NAV text files (NAVD / NAVN)
    source_zips/  — original zip files as downloaded from DOR

Additional folders:
    data/raw/_unsorted/   — files on disk that have not yet been assigned
                            to a county folder (nothing is ever deleted)
"""
from __future__ import annotations

import sys
from pathlib import Path

# ── path bootstrap ─────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ── county registry ────────────────────────────────────────────────────────────
# Copied directly from scripts/seeds/seed_counties.py so this script has
# zero runtime dependencies — no DB, no settings, no imports beyond stdlib.
FL_COUNTIES = [
    ("12001", "Alachua"),
    ("12003", "Baker"),
    ("12005", "Bay"),
    ("12007", "Bradford"),
    ("12009", "Brevard"),
    ("12011", "Broward"),
    ("12013", "Calhoun"),
    ("12015", "Charlotte"),
    ("12017", "Citrus"),
    ("12019", "Clay"),
    ("12021", "Collier"),
    ("12023", "Columbia"),
    ("12086", "Miami-Dade"),
    ("12027", "DeSoto"),
    ("12029", "Dixie"),
    ("12031", "Duval"),
    ("12033", "Escambia"),
    ("12035", "Flagler"),
    ("12037", "Franklin"),
    ("12039", "Gadsden"),
    ("12041", "Gilchrist"),
    ("12043", "Glades"),
    ("12045", "Gulf"),
    ("12047", "Hamilton"),
    ("12049", "Hardee"),
    ("12051", "Hendry"),
    ("12053", "Hernando"),
    ("12055", "Highlands"),
    ("12057", "Hillsborough"),
    ("12059", "Holmes"),
    ("12061", "Indian River"),
    ("12063", "Jackson"),
    ("12065", "Jefferson"),
    ("12067", "Lafayette"),
    ("12069", "Lake"),
    ("12071", "Lee"),
    ("12073", "Leon"),
    ("12075", "Levy"),
    ("12077", "Liberty"),
    ("12079", "Madison"),
    ("12081", "Manatee"),
    ("12083", "Marion"),
    ("12085", "Martin"),
    ("12087", "Monroe"),
    ("12089", "Nassau"),
    ("12091", "Okaloosa"),
    ("12093", "Okeechobee"),
    ("12095", "Orange"),
    ("12097", "Osceola"),
    ("12099", "Palm Beach"),
    ("12101", "Pasco"),
    ("12103", "Pinellas"),
    ("12105", "Polk"),
    ("12107", "Putnam"),
    ("12109", "Saint Johns"),
    ("12111", "Saint Lucie"),
    ("12113", "Santa Rosa"),
    ("12115", "Sarasota"),
    ("12117", "Seminole"),
    ("12119", "Sumter"),
    ("12121", "Suwannee"),
    ("12123", "Taylor"),
    ("12125", "Union"),
    ("12127", "Volusia"),
    ("12129", "Wakulla"),
    ("12131", "Walton"),
    ("12133", "Washington"),
]

COUNTY_SUBFOLDERS = ["nal", "sdf", "gis", "nav", "source_zips"]


def county_folder_name(fips: str, name: str) -> str:
    """
    Canonical folder key: {fips}_{snake_case_name}
    Handles spaces, hyphens, and mixed case.
    Examples:
        12033, Escambia      -> 12033_escambia
        12086, Miami-Dade    -> 12086_miami_dade
        12061, Indian River  -> 12061_indian_river
        12109, Saint Johns   -> 12109_saint_johns
        12027, DeSoto        -> 12027_desoto
    """
    snake = name.lower().replace("-", "_").replace(" ", "_")
    return f"{fips}_{snake}"


def main() -> None:
    raw_dir = ROOT / "data" / "raw"

    counties_dir = raw_dir / "counties"
    unsorted_dir = raw_dir / "_unsorted"

    created_dirs: list[Path] = []
    skipped_dirs: list[Path] = []

    # ── county folders ─────────────────────────────────────────────────────── #
    for fips, name in FL_COUNTIES:
        folder_key = county_folder_name(fips, name)
        county_root = counties_dir / folder_key

        for subfolder in COUNTY_SUBFOLDERS:
            target = county_root / subfolder
            if not target.exists():
                target.mkdir(parents=True, exist_ok=True)
                created_dirs.append(target)
            else:
                skipped_dirs.append(target)

    # ── _unsorted folder ───────────────────────────────────────────────────── #
    if not unsorted_dir.exists():
        unsorted_dir.mkdir(parents=True, exist_ok=True)
        created_dirs.append(unsorted_dir)
    else:
        skipped_dirs.append(unsorted_dir)

    # ── summary ────────────────────────────────────────────────────────────── #
    print(f"Done.")
    print(f"  Counties processed : {len(FL_COUNTIES)}")
    print(f"  Directories created: {len(created_dirs)}")
    print(f"  Already existed    : {len(skipped_dirs)}")
    print(f"  Root               : {counties_dir}")
    print()

    if created_dirs:
        print("Created:")
        for d in created_dirs:
            print(f"  + {d.relative_to(ROOT)}")

    if skipped_dirs:
        print(f"\nSkipped (already existed): {len(skipped_dirs)} directories")


if __name__ == "__main__":
    main()
