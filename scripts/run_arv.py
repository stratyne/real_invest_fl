"""
scripts/run_arv.py
-------------------
Entry point for the ARV calculation pipeline.

Delegates entirely to real_invest_fl.ingest.arv_calculator.

Usage:
    python scripts/run_arv.py
    python scripts/run_arv.py --dry-run
    python scripts/run_arv.py --force
    python scripts/run_arv.py --batch-size 1000
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from real_invest_fl.ingest.arv_calculator import main  # noqa: E402

if __name__ == "__main__":
    main()
