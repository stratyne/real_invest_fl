"""
NAL row → Property column mapper.

Maps a raw NAL CSV row (dict of string values) to a dict of
Property column name → typed Python value, ready for SQLAlchemy
upsert. Also computes all derived fields.
"""
from __future__ import annotations
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


def map_nal_row(
    row: dict,
    county_fips: str,
    absentee_owner: bool,
) -> dict:
    """
    Map one NAL CSV row to a Property column dict.

    Args:
        row:           Raw NAL row as dict[str, str].
        county_fips:   County FIPS code — '12033' for Escambia.
        absentee_owner: Pre-computed absentee flag from nal_filter.

    Returns:
        Dict of Property column name → typed value.
        All values are Python-native types ready for SQLAlchemy.
    """
    return {
        # ---------------------------------------------------------- #
        # Primary key                                                  #
        # ---------------------------------------------------------- #
        "county_fips": county_fips,
        "parcel_id":   _str(row.get("PARCEL_ID")),

        # ---------------------------------------------------------- #
        # NAL identification                                           #
        # ---------------------------------------------------------- #
        "co_no":       _int(row.get("CO_NO")),
        "asmnt_yr":    _int(row.get("ASMNT_YR")),
        "dor_uc":      _dor_uc(row.get("DOR_UC")),
        "pa_uc":       _str_max(row.get("PA_UC"), 10),
        "state_par_id": _str_max(row.get("STATE_PAR_ID"), 30),

        # ---------------------------------------------------------- #
        # NAL value fields                                             #
        # ---------------------------------------------------------- #
        "jv":          _int(row.get("JV")),
        "av_nsd":      _int(row.get("AV_NSD")),
        "tv_nsd":      _int(row.get("TV_NSD")),
        "av_sd":       _int(row.get("AV_SD")),
        "tv_sd":       _int(row.get("TV_SD")),
        "jv_hmstd":    _int(row.get("JV_HMSTD")),
        "lnd_val":     _int(row.get("LND_VAL")),
        "exmpt_01":    _int(row.get("EXMPT_01")),

        # ---------------------------------------------------------- #
        # NAL land and improvement                                     #
        # ---------------------------------------------------------- #
        "lnd_sqfoot":   _int(row.get("LND_SQFOOT")),
        "imp_qual":     _int(row.get("IMP_QUAL")),
        "const_class":  _int(row.get("CONST_CLASS")),
        "eff_yr_blt":   _int(row.get("EFF_YR_BLT")),
        "act_yr_blt":   _int(row.get("ACT_YR_BLT")),
        "tot_lvg_area": _int(row.get("TOT_LVG_AREA")),
        "no_buldng":    _int(row.get("NO_BULDNG")),
        "no_res_unts":  _int(row.get("NO_RES_UNTS")),
        "spec_feat_val": _int(row.get("SPEC_FEAT_VAL")),
        "dt_last_inspt": _str_max(row.get("DT_LAST_INSPT"), 4),

        # ---------------------------------------------------------- #
        # NAL condition and disaster flags                             #
        # ---------------------------------------------------------- #
        "nconst_val":  _int(row.get("NCONST_VAL")),
        "del_val":     _int(row.get("DEL_VAL")),
        "par_splt":    _str_max(row.get("PAR_SPLT"), 5),
        "distr_cd":    _int(row.get("DISTR_CD")),
        "distr_yr":    _int(row.get("DISTR_YR")),
        "spass_cd":    _str_max(row.get("SPASS_CD"), 1),

        # ---------------------------------------------------------- #
        # NAL embedded sale history — Sale 1                          #
        # ---------------------------------------------------------- #
        "multi_par_sal1": _str_max(row.get("MULTI_PAR_SAL1"), 1),
        "qual_cd1":       _str_max(row.get("QUAL_CD1"), 2),
        "vi_cd1":         _str_max(row.get("VI_CD1"), 1),
        "sale_prc1":      _int(row.get("SALE_PRC1")),
        "sale_yr1":       _int(row.get("SALE_YR1")),
        "sale_mo1":       _int(row.get("SALE_MO1")),
        "sal_chng_cd1":   _str_max(row.get("SAL_CHNG_CD1"), 1),

        # ---------------------------------------------------------- #
        # NAL embedded sale history — Sale 2                          #
        # ---------------------------------------------------------- #
        "multi_par_sal2": _str_max(row.get("MULTI_PAR_SAL2"), 1),
        "qual_cd2":       _str_max(row.get("QUAL_CD2"), 2),
        "vi_cd2":         _str_max(row.get("VI_CD2"), 1),
        "sale_prc2":      _int(row.get("SALE_PRC2")),
        "sale_yr2":       _int(row.get("SALE_YR2")),
        "sale_mo2":       _int(row.get("SALE_MO2")),
        "sal_chng_cd2":   _str_max(row.get("SAL_CHNG_CD2"), 1),

        # ---------------------------------------------------------- #
        # NAL owner                                                    #
        # ---------------------------------------------------------- #
        "own_name":      _str_max(row.get("OWN_NAME"), 50),
        "own_addr1":     _str_max(row.get("OWN_ADDR1"), 40),
        "own_addr2":     _str_max(row.get("OWN_ADDR2"), 40),
        "own_city":      _str_max(row.get("OWN_CITY"), 40),
        "own_state":     _str_max(row.get("OWN_STATE"), 25),
        "own_zipcd":     _str_max(row.get("OWN_ZIPCD"), 5),
        "own_state_dom": _str_max(row.get("OWN_STATE_DOM"), 2),

        # ---------------------------------------------------------- #
        # NAL physical address                                         #
        # ---------------------------------------------------------- #
        "phy_addr1": _str_max(row.get("PHY_ADDR1"), 40),
        "phy_city":  _str_max(row.get("PHY_CITY"), 40),
        "phy_zipcd": _str_max(row.get("PHY_ZIPCD"), 5),

        # ---------------------------------------------------------- #
        # NAL geographic                                               #
        # ---------------------------------------------------------- #
        "mkt_ar":    _str_max(row.get("MKT_AR"), 3),
        "nbrhd_cd":  _str_max(row.get("NBRHD_CD"), 10),
        "twn":       _str_max(row.get("TWN"), 3),
        "rng":       _str_max(row.get("RNG"), 3),
        "sec":       _str_max(row.get("SEC"), 3),
        "census_bk": _str_max(row.get("CENSUS_BK"), 16),
        "alt_key":   _str_max(row.get("ALT_KEY"), 26),
        "s_legal":   _str_max(row.get("S_LEGAL"), 30),

        # ---------------------------------------------------------- #
        # Derived fields                                               #
        # ---------------------------------------------------------- #
        "absentee_owner": absentee_owner,

        "improvement_to_land_ratio": _improvement_to_land_ratio(
            jv=_int(row.get("JV")),
            lnd_val=_int(row.get("LND_VAL")),
        ),
        "soh_compression_ratio": _soh_compression_ratio(
            av_nsd=_int(row.get("AV_NSD")),
            jv=_int(row.get("JV")),
        ),
        "years_since_last_sale": _years_since_last_sale(
            asmnt_yr=_int(row.get("ASMNT_YR")),
            sale_yr1=_int(row.get("SALE_YR1")),
        ),
    }


# ------------------------------------------------------------------ #
# Derived field calculations                                           #
# ------------------------------------------------------------------ #

def _improvement_to_land_ratio(
    jv: int | None,
    lnd_val: int | None,
) -> Decimal | None:
    """
    (JV - LND_VAL) / LND_VAL
    Capped at 9999.9999 to fit NUMERIC(8, 4).
    Returns None if inputs are missing or land value is zero.
    """
    if jv is None or lnd_val is None or lnd_val == 0:
        return None
    try:
        ratio = (jv - lnd_val) / lnd_val
        # Cap to fit NUMERIC(8, 4) — values beyond this are anomalous
        ratio = min(ratio, Decimal("9999.9999"))
        ratio = max(ratio, Decimal("-9999.9999"))
        return Decimal(str(round(ratio, 4)))
    except Exception:
        return None


def _soh_compression_ratio(
    av_nsd: int | None,
    jv: int | None,
) -> Decimal | None:
    """
    AV_NSD / JV
    Approaches 1.0 when SOH cap is not constraining.
    Low values indicate long-term homestead owner — seller motivation signal.
    Returns None if inputs are missing or JV is zero.
    """
    if av_nsd is None or jv is None or jv == 0:
        return None
    try:
        ratio = av_nsd / jv
        return Decimal(str(round(ratio, 4)))
    except Exception:
        return None


def _years_since_last_sale(
    asmnt_yr: int | None,
    sale_yr1: int | None,
) -> int | None:
    """
    ASMNT_YR - SALE_YR1
    Higher values indicate long-term ownership — seller motivation signal.
    Returns None if either input is missing.
    """
    if asmnt_yr is None or sale_yr1 is None:
        return None
    result = asmnt_yr - sale_yr1
    return result if result >= 0 else None


# ------------------------------------------------------------------ #
# Type coercion helpers                                                #
# ------------------------------------------------------------------ #

def _str_max(val, max_len: int) -> str | None:
    """Safely coerce to string and truncate to max_len."""
    s = _str(val)
    if s is None:
        return None
    return s[:max_len]


def _int(val) -> int | None:
    """Safely coerce to int. Returns None on failure or zero."""
    if val is None:
        return None
    try:
        v = int(float(str(val).strip()))
        return v if v != 0 else None
    except (ValueError, TypeError):
        return None


def _str(val) -> str | None:
    """Safely coerce to stripped string. Returns None if empty."""
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None

def _dor_uc(val) -> str | None:
    """
    Normalize DOR use code to zero-padded three digits.

    Florida DOR specifies use codes as three-digit values (001, 002, etc.).
    Some county NAL files ship unpadded integers (1, 2, 93). This function
    normalizes all variants to '001', '002', '093' etc. for consistent
    querying across all 67 counties.

    Returns None if the value is missing or non-numeric.
    """
    s = _str(val)
    if s is None:
        return None
    try:
        return str(int(s)).zfill(3)
    except ValueError:
        return None
