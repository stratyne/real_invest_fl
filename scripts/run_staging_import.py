"""
scripts/run_staging_import.py
------------------------------
Entry point for all staging file-drop parsers.

Runs all three parsers in sequence, or a specific one via --source flag.

Usage:
    python scripts/run_staging_import.py                    # all sources
    python scripts/run_staging_import.py --source lis_pendens
    python scripts/run_staging_import.py --source foreclosure
    python scripts/run_staging_import.py --source tax_deed
    python scripts/run_staging_import.py --dry-run
    python scripts/run_staging_import.py --source lis_pendens --dry-run
    python scripts/run_staging_import.py --source lis_pendens --file path/to/file.xlsx
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run staging file-drop parsers for government data sources."
    )
    parser.add_argument(
        "--source",
        choices=["lis_pendens", "foreclosure", "tax_deed", "all"],
        default="all",
        help="Which parser to run (default: all).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Parse and match but do not write to the database.",
    )
    parser.add_argument(
        "--file", type=Path, default=None,
        help="Process a single specific file (only valid with --source).",
    )
    args = parser.parse_args()

    if args.file and args.source == "all":
        parser.error("--file requires --source to be specified (not 'all')")

    sources = (
        [args.source] if args.source != "all"
        else ["lis_pendens", "foreclosure", "tax_deed"]
    )

    for source in sources:
        print(f"\n{'='*60}")
        print(f"  Running parser: {source}")
        print(f"{'='*60}")

        if source == "lis_pendens":
            from real_invest_fl.ingest.staging_parsers.lis_pendens_parser import (
                run_lis_pendens_import,
            )
            run_lis_pendens_import(dry_run=args.dry_run, specific_file=args.file)

        elif source == "foreclosure":
            from real_invest_fl.ingest.staging_parsers.foreclosure_parser import (
                run_foreclosure_import,
            )
            run_foreclosure_import(dry_run=args.dry_run, specific_file=args.file)

        elif source == "tax_deed":
            from real_invest_fl.ingest.staging_parsers.tax_deed_parser import (
                run_tax_deed_import,
            )
            run_tax_deed_import(dry_run=args.dry_run, specific_file=args.file)


if __name__ == "__main__":
    main()
