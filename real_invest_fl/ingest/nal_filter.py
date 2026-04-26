"""
NAL filter evaluator.

Evaluates a single NAL row (as a dict) against a filter_criteria
JSONB document loaded from the filter_profiles table.

Returns (passed: bool, rejection_reasons: list[str])

Only Stage 1 NAL-available fields are evaluated here.
CAMA fields (foundation, exterior_wall, bedrooms, bathrooms)
are evaluated in Stage 2.
"""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)


def evaluate_nal(row: dict, criteria: dict) -> tuple[bool, list[str]]:
    """
    Evaluate a NAL row against filter_criteria.

    Args:
        row:      Dict of NAL field name → value for one parcel.
        criteria: The filter_criteria JSONB document from filter_profiles.

    Returns:
        (passed, rejection_reasons)
        passed is True only if all applicable NAL filters pass.
        rejection_reasons is empty when passed is True.
    """
    rejections: list[str] = []
    f = criteria.get("filters", {})

    # ------------------------------------------------------------------ #
    # DOR use code                                                         #
    # NAL field: DOR_UC (integer in file)                                 #
    # ------------------------------------------------------------------ #
    dor_uc_filter = f.get("dor_use_code", {})
    include = dor_uc_filter.get("include")
    if include is not None:
        val = _int(row.get("DOR_UC"))
        if val is None or val not in include:
            rejections.append("dor_uc_mismatch")

    # ------------------------------------------------------------------ #
    # Year built                                                           #
    # NAL field: ACT_YR_BLT                                               #
    # ------------------------------------------------------------------ #
    yr_filter = f.get("year_built", {})
    yr_min = yr_filter.get("min")
    yr_max = yr_filter.get("max")
    if yr_min is not None or yr_max is not None:
        val = _int(row.get("ACT_YR_BLT"))
        if val is None:
            rejections.append("year_built_missing")
        else:
            if yr_min is not None and val < yr_min:
                rejections.append("year_built_too_old")
            if yr_max is not None and val > yr_max:
                rejections.append("year_built_too_new")

    # ------------------------------------------------------------------ #
    # Improvement quality                                                  #
    # NAL field: IMP_QUAL                                                  #
    # ------------------------------------------------------------------ #
    iq_filter = f.get("imp_qual", {})
    iq_min = iq_filter.get("min")
    iq_max = iq_filter.get("max")
    if iq_min is not None or iq_max is not None:
        val = _int(row.get("IMP_QUAL"))
        if val is None:
            pass  # IMP_QUAL is optional — do not reject on missing
        else:
            if iq_min is not None and val < iq_min:
                rejections.append("imp_qual_too_low")
            if iq_max is not None and val > iq_max:
                rejections.append("imp_qual_too_high")

    # ------------------------------------------------------------------ #
    # Living area                                                          #
    # NAL field: TOT_LVG_AREA                                             #
    # ------------------------------------------------------------------ #
    la_filter = f.get("living_area_sqft", {})
    la_min = la_filter.get("min")
    la_max = la_filter.get("max")
    if la_min is not None or la_max is not None:
        val = _int(row.get("TOT_LVG_AREA"))
        if val is None:
            rejections.append("living_area_missing")
        else:
            if la_min is not None and val < la_min:
                rejections.append("living_area_too_small")
            if la_max is not None and val > la_max:
                rejections.append("living_area_too_large")

    # ------------------------------------------------------------------ #
    # Just value                                                           #
    # NAL field: JV                                                        #
    # ------------------------------------------------------------------ #
    jv_filter = f.get("just_value", {})
    jv_min = jv_filter.get("min")
    jv_max = jv_filter.get("max")
    if jv_min is not None or jv_max is not None:
        val = _int(row.get("JV"))
        if val is None:
            rejections.append("just_value_missing")
        else:
            if jv_min is not None and val < jv_min:
                rejections.append("just_value_too_low")
            if jv_max is not None and val > jv_max:
                rejections.append("just_value_too_high")

    # ------------------------------------------------------------------ #
    # Number of buildings                                                  #
    # NAL field: NO_BULDNG                                                 #
    # ------------------------------------------------------------------ #
    nb_filter = f.get("num_buildings", {})
    nb_max = nb_filter.get("max")
    if nb_max is not None:
        val = _int(row.get("NO_BULDNG"))
        if val is not None and val > nb_max:
            rejections.append("num_buildings_exceeded")

    # ------------------------------------------------------------------ #
    # Number of residential units                                          #
    # NAL field: NO_RES_UNTS                                              #
    # ------------------------------------------------------------------ #
    nu_filter = f.get("num_residential_units", {})
    nu_max = nu_filter.get("max")
    if nu_max is not None:
        val = _int(row.get("NO_RES_UNTS"))
        if val is not None and val > nu_max:
            rejections.append("num_res_units_exceeded")

    # ------------------------------------------------------------------ #
    # County number                                                        #
    # NAL field: CO_NO                                                     #
    # ------------------------------------------------------------------ #
    co_filter = f.get("county_nos", {})
    co_include = co_filter.get("include")
    if co_include is not None:
        val = _int(row.get("CO_NO"))
        if val is None or val not in co_include:
            rejections.append("county_no_mismatch")

    # ------------------------------------------------------------------ #
    # ZIP codes                                                            #
    # NAL field: PHY_ZIPCD                                                 #
    # ------------------------------------------------------------------ #
    zip_filter = f.get("zip_codes", {})
    zip_include = zip_filter.get("include")
    if zip_include is not None:
        val = _str(row.get("PHY_ZIPCD"))
        if val is None or val not in zip_include:
            rejections.append("zip_code_excluded")

    # ------------------------------------------------------------------ #
    # Absentee owner                                                       #
    # Derived field — computed from mailing vs physical address           #
    # ------------------------------------------------------------------ #
    ab_filter = f.get("absentee_owner", {})
    ab_required = ab_filter.get("required")
    if ab_required is not None:
        absentee = _is_absentee(row)
        if ab_required is True and not absentee:
            rejections.append("absentee_owner_required")
        elif ab_required is False and absentee:
            rejections.append("owner_occupied_required")

    # ------------------------------------------------------------------ #
    # Disaster code                                                        #
    # NAL field: DISTR_CD                                                  #
    # ------------------------------------------------------------------ #
    dc_filter = f.get("disaster_code_present", {})
    dc_required = dc_filter.get("required")
    if dc_required is False:
        val = _int(row.get("DISTR_CD"))
        if val is not None and val > 0:
            rejections.append("disaster_code_present")

    passed = len(rejections) == 0
    return passed, rejections


# ------------------------------------------------------------------ #
# Private helpers                                                      #
# ------------------------------------------------------------------ #

def _int(val) -> int | None:
    """Safely coerce a value to int. Returns None on failure."""
    if val is None:
        return None
    try:
        v = int(val)
        return v if v > 0 else None
    except (ValueError, TypeError):
        return None


def _str(val) -> str | None:
    """Safely coerce a value to stripped string. Returns None if empty."""
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def _is_absentee(row: dict) -> bool:
    """
    Derive absentee owner flag.
    True when owner mailing address differs from physical address.
    Compares OWN_ADDR1 + OWN_ZIPCD vs PHY_ADDR1 + PHY_ZIPCD.
    Case-insensitive, whitespace-normalized.
    """
    own_addr = _str(row.get("OWN_ADDR1")) or ""
    own_zip = _str(row.get("OWN_ZIPCD")) or ""
    phy_addr = _str(row.get("PHY_ADDR1")) or ""
    phy_zip = _str(row.get("PHY_ZIPCD")) or ""

    if not own_addr or not phy_addr:
        return False

    return (
        own_addr.upper() != phy_addr.upper()
        or own_zip != phy_zip
    )
