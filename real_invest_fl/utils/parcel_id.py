"""
Parcel ID normalization — handles format differences between NAL and CAMA exports.
Escambia County NAL uses a numeric string; CAMA may include dashes or spaces.
Normalization: strip all non-alphanumeric characters, upper-case, zero-pad to 18 chars.
This strategy is documented here so county-specific variations can be added without
touching calling code — add a county_fips branch below if a new county deviates.
"""
import re

_NON_ALNUM = re.compile(r"[^A-Z0-9]")


def normalize_parcel_id(raw: str, county_fips: str = "12033") -> str:
    """Return a normalized parcel ID string suitable for use as a join key."""
    cleaned = _NON_ALNUM.sub("", raw.upper())
    # Escambia (12033): pad to 18 characters
    if county_fips == "12033":
        return cleaned.zfill(18)
    # Default: return cleaned without padding (extend for other counties)
    return cleaned
