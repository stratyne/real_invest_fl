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


# ---------------------------------------------------------------------------
# Street address normalization
# ---------------------------------------------------------------------------

# USPS street suffix abbreviation map.
# NAL phy_addr1 stores abbreviated forms — normalize incoming addresses to match.
# Keys are full forms as they appear in scraped/source data.
# Values are the canonical NAL abbreviations.
_STREET_SUFFIX_MAP: dict[str, str] = {
    "ROAD":       "RD",
    "STREET":     "ST",
    "AVENUE":     "AVE",
    "BOULEVARD":  "BLVD",
    "DRIVE":      "DR",
    "COURT":      "CT",
    "PLACE":      "PL",
    "LANE":       "LN",
    "CIRCLE":     "CIR",
    "TRAIL":      "TRL",
    "TERRACE":    "TER",
    "HIGHWAY":    "HWY",
    "PARKWAY":    "PKWY",
    "EXPRESSWAY": "EXPY",
    "FREEWAY":    "FWY",
}

# Directional words that may appear as the first token of the street name
# (after the house number) in scraped source data but are absent in NAL.
# NAL stores abbreviated directionals (N, S, E, W) as part of the street
# name itself — it does NOT use full words as a leading prefix.
# We contract full-word directionals to their abbreviations so that
# "NORTH PALAFOX ST" becomes "N PALAFOX ST" to match NAL storage.
# Single-letter abbreviations are passed through unchanged.
_DIRECTIONAL_MAP: dict[str, str] = {
    "NORTH":     "N",
    "SOUTH":     "S",
    "EAST":      "E",
    "WEST":      "W",
    "NORTHEAST": "NE",
    "NORTHWEST": "NW",
    "SOUTHEAST": "SE",
    "SOUTHWEST": "SW",
}

# Unit designator patterns — stripped before digit-letter injection.
# Two branches: keyword-led designators (word boundary safe) and bare #.
_UNIT_RE = re.compile(
    r"(?:"
    r"\b(?:APT\.?|UNIT|STE|SUITE)\s+[\w-]+"   # keyword + space + unit value
    r"|"
    r"#\s*[\w-]+"                              # bare # + unit value (no \b)
    r")",
    re.IGNORECASE,
)

# Digit-to-letter injection — inject space between a digit and a letter
# EXCEPT when the letter sequence is an ordinal suffix (ST, ND, RD, TH).
# Applied after upper-casing so the negative lookahead is case-safe.
# Digit-to-letter injection — Inject space between digit and letter EXCEPT 
# before ordinal suffixes (ST, ND, RD, TH). The lookahead sits between the digit and the letter
# digit and the letter so it can inspect the full two-character ordinal token.
_DIGIT_LETTER_RE = re.compile(r"(\d)(?!(?:ST|ND|RD|TH)\b)([A-Z])")

# Suffix map compiled to a single regex for whole-word replacement.
# Matches only when the suffix token stands alone (word boundary on both sides).
_SUFFIX_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _STREET_SUFFIX_MAP) + r")\b"
)

# Directional map compiled for the first-token-of-street-name position only.
# Pattern: house number, whitespace, full directional word, whitespace.
# We build one pattern per direction and apply them in order.
_DIRECTIONAL_FULL_WORDS = set(_DIRECTIONAL_MAP.keys())


def normalize_street_address(addr: str, strip_unit: bool = True) -> str:
    """
    Normalize a street address string for matching against NAL phy_addr1.

    Transformations applied in order:
        1. Collapse whitespace and upper-case
        2. Strip unit designators                     (APT 4, UNIT B, #12, SUITE 2A)
        3. Inject space between digit run and letter  (2301W -> 2301 W)
           — ordinal suffixes (74TH, 48TH) are excluded from injection
        4. Collapse whitespace again after injection
        5. Expand street suffix to NAL abbreviation   (ROAD -> RD)
        6. Contract full directional word to abbrev   (NORTH -> N)
           — only when it is the first token of the street name

    Does NOT zero-pad or otherwise modify the house number.
    Does NOT alter single-letter directional abbreviations (N, S, E, W).
    Thread-safe — no mutable state.

    Args:
        addr: Raw address string from any scraping source.

    Returns:
        Normalized uppercase address string suitable for comparison
        against properties.phy_addr1.

    Examples:
        >>> normalize_street_address("110 Frisco Road")
        '110 FRISCO RD'
        >>> normalize_street_address("5931 Muldoon Road")
        '5931 MULDOON RD'
        >>> normalize_street_address("905 N 74th Ave")
        '905 N 74TH AVE'
        >>> normalize_street_address("2301 W Michigan Ave 51")
        '2301 W MICHIGAN AVE 51'
    """
    if not addr:
        return ""

    # Step 1 — collapse whitespace and upper-case
    addr = re.sub(r"\s+", " ", addr.upper().strip())

    # Step 2 — strip unit designators (before digit-letter injection
    # so that 'SUITE 2A' is consumed whole, not split into '2' and 'A')
    if strip_unit:
        addr = _UNIT_RE.sub("", addr)
        addr = re.sub(r"\s+", " ", addr.strip())

    # Step 3 — inject space between digit and letter, excluding ordinals
    addr = _DIGIT_LETTER_RE.sub(r"\1 \2", addr)

    # Step 4 — collapse whitespace again after injection
    addr = re.sub(r"\s+", " ", addr.strip())

    # Step 5 — expand street suffixes to NAL abbreviations
    addr = _SUFFIX_RE.sub(lambda m: _STREET_SUFFIX_MAP[m.group(1)], addr)
    addr = re.sub(r"\s+", " ", addr.strip())

    # Step 6 — contract full directional word that is the first token
    # of the street name (immediately after the house number).
    for full, abbr in _DIRECTIONAL_MAP.items():
        not_another_dir = "(?!" + "|".join(
            re.escape(d) + r"\b" for d in _DIRECTIONAL_FULL_WORDS
        ) + ")"
        pattern = re.compile(
            r"^(\d+\s+)" + re.escape(full) + r"\s+" + not_another_dir
        )
        addr = pattern.sub(r"\1" + abbr + " ", addr)

    return re.sub(r"\s+", " ", addr.strip())
