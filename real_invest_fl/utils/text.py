"""Stateless text cleaning and parsing utilities."""
import re

WHITESPACE_RE = re.compile(r"\s+")
PRICE_RE = re.compile(r"[\$,]")
NUMBER_RE = re.compile(r"[^\d.]")


def clean_text(value: str) -> str:
    """Trim and collapse internal whitespace."""
    return WHITESPACE_RE.sub(" ", (value or "").strip())


def parse_money(value: str) -> float | None:
    """Return float from a price string, or None if unparseable."""
    try:
        return float(PRICE_RE.sub("", value).strip())
    except (ValueError, AttributeError):
        return None


def parse_number(value: str) -> float | None:
    """Return float from a numeric string, or None if unparseable."""
    try:
        return float(NUMBER_RE.sub("", value).strip())
    except (ValueError, AttributeError):
        return None


def normalize_keyword_text(*parts: str) -> str:
    """Join, lower-case, and clean multiple strings for keyword matching."""
    return clean_text(" ".join(str(p) for p in parts)).lower()


def first_non_empty(*values: str) -> str:
    """Return the first non-empty cleaned string from an iterable."""
    for v in values:
        cleaned = clean_text(str(v))
        if cleaned:
            return cleaned
    return ""
