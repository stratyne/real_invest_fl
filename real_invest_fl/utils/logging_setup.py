"""Rotating file + console log handler setup."""
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(log_level: str = "INFO", log_dir: Path = Path("./logs")) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "real_invest_fl.log"

    fmt = logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)

    rotating = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    rotating.setFormatter(fmt)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(console)
    root.addHandler(rotating)
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))
