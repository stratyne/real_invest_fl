"""
Properties routes — profile-driven multi-county search and single-parcel detail.

GET /properties
    Loads the specified filter profile, validates access to all counties
    in the profile, builds a query-time WHERE clause from filter_criteria,
    computes deal score, returns a single page of results ranked by deal
    score descending (or the configured sort field).

    Architecture — Option C hybrid:
    1. SQL fetches scoring columns only (lightweight) for all filtered rows.
    2. SQL fetches latest listing_event scoring columns for those parcels.
    3. Python scores, filters, sorts the full ID list.
    4. SQL fetches full Property ORM objects for the current page slice only.
    5. Python builds the response from the page slice.

GET /{county_fips}/properties/{parcel_id}
    Returns full property detail for a single parcel, including the most
    recent listing_event if one exists.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, NamedTuple

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from collections import defaultdict

from real_invest_fl.api.deps import county_access, get_current_user, get_db
from real_invest_fl.db.models.filter_profile import FilterProfile
from real_invest_fl.db.models.listing_event import ListingEvent
from real_invest_fl.db.models.property import Property
from real_invest_fl.db.models.user import User
from real_invest_fl.db.models.user_profile_prefs import UserProfilePrefs
from real_invest_fl.db.models.user_county_access import UserCountyAccess

router = APIRouter(tags=["properties"])


# ── Lightweight row types for scoring pass ───────────────────────────────

class _ScoringRow(NamedTuple):
    county_fips: str
    parcel_id: str
    arv_spread: int | None
    jv: int | None
    absentee_owner: bool | None
    list_price: int | None
    years_since_last_sale: int | None
    tot_lvg_area: int | None
    act_yr_blt: int | None
    phy_addr1: str | None


class _EventScoringRow(NamedTuple):
    county_fips: str
    parcel_id: str
    signal_tier: int | None
    days_on_market: int | None
    listing_type: str | None
    arv_estimate: int | None
    arv_source: str | None
    arv_spread: int | None


# ── Access helpers ───────────────────────────────────────────────────────

def _assert_county_access(
    requested_fips: list[str],
    accessible_fips: set[str],
    is_superuser: bool,
) -> None:
    if is_superuser:
        return
    denied = [f for f in requested_fips if f not in accessible_fips]
    if denied:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied for counties: {', '.join(denied)}",
        )


async def _get_accessible_fips(
    current_user: User,
    db: AsyncSession,
) -> set[str]:
    result = await db.execute(
        select(UserCountyAccess.county_fips).where(
            UserCountyAccess.user_id == current_user.id
        )
    )
    return set(result.scalars().all())


async def _get_visible_active_profile(
    filter_profile_id: int,
    current_user: User,
    db: AsyncSession,
) -> FilterProfile:
    result = await db.execute(
        select(FilterProfile).where(
            FilterProfile.id == filter_profile_id,
            FilterProfile.is_active.is_(True),
        )
    )
    profile: FilterProfile | None = result.scalar_one_or_none()

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Filter profile {filter_profile_id} not found",
        )

    if not current_user.is_superuser:
        if profile.user_id is not None and profile.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Filter profile {filter_profile_id} not found",
            )
        accessible = await _get_accessible_fips(current_user, db)
        _assert_county_access(profile.county_fips, accessible, current_user.is_superuser)

    return profile


# ── Response schemas ─────────────────────────────────────────────────────

class ListingEventSummary(BaseModel):
    id: int
    signal_tier: int | None
    signal_type: str | None
    listing_type: str | None
    list_price: int | None
    list_date: Any | None
    days_on_market: int | None
    arv_estimate: int | None
    arv_source: str | None
    arv_spread: int | None
    workflow_status: str
    source: str | None
    listing_url: str | None

    model_config = {"from_attributes": True}


class PropertySearchResult(BaseModel):
    county_fips: str
    parcel_id: str
    phy_addr1: str | None
    phy_city: str | None
    phy_zipcd: str | None
    dor_uc: str | None
    jv: int | None
    tot_lvg_area: int | None
    lnd_sqfoot: int | None
    act_yr_blt: int | None
    eff_yr_blt: int | None
    bedrooms: int | None
    bathrooms: float | None
    absentee_owner: bool | None
    imp_qual: int | None
    years_since_last_sale: int | None
    improvement_to_land_ratio: float | None
    soh_compression_ratio: float | None
    arv_estimate: int | None
    arv_spread: int | None
    jv_per_sqft: float | None
    deal_score: float | None
    arv_source: str | None
    latitude: float | None
    longitude: float | None
    latest_listing: ListingEventSummary | None

    model_config = {"from_attributes": True}


class PaginatedPropertySearchResult(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    results: list[PropertySearchResult]


class PropertyDetail(BaseModel):
    county_fips: str
    parcel_id: str
    state_par_id: str
    phy_addr1: str | None
    phy_city: str | None
    phy_zipcd: str | None
    own_name: str | None
    own_addr1: str | None
    own_city: str | None
    own_state: str | None
    own_zipcd: str | None
    absentee_owner: bool | None
    dor_uc: str | None
    pa_uc: str | None
    jv: int | None
    av_nsd: int | None
    lnd_val: int | None
    nav_total_assessment: float | None
    tot_lvg_area: int | None
    lnd_sqfoot: int | None
    act_yr_blt: int | None
    eff_yr_blt: int | None
    const_class: int | None
    imp_qual: int | None
    bedrooms: int | None
    bathrooms: float | None
    foundation_type: str | None
    exterior_wall: str | None
    roof_type: str | None
    cama_quality_code: str | None
    cama_condition_code: str | None
    no_buldng: int | None
    no_res_unts: int | None
    mkt_ar: str | None
    nbrhd_cd: str | None
    census_bk: str | None
    zoning: str | None
    years_since_last_sale: int | None
    improvement_to_land_ratio: float | None
    soh_compression_ratio: float | None
    spec_feat_val: int | None
    jv_per_sqft: float | None
    arv_estimate: int | None
    arv_spread: int | None
    qual_cd1: str | None
    sale_prc1: int | None
    sale_yr1: int | None
    sale_mo1: int | None
    qual_cd2: str | None
    sale_prc2: int | None
    sale_yr2: int | None
    sale_mo2: int | None
    latitude: float | None
    longitude: float | None
    nal_ingested_at: datetime | None
    cama_enriched_at: datetime | None
    latest_listing: ListingEventSummary | None

    model_config = {"from_attributes": True}


class InlineSearchRequest(BaseModel):
    """Inline search payload — no profile is written.

    county_fips: list of FIPS codes the search spans. User must have
    access to all of them.
    filter_criteria: same structure as filter_profile.filter_criteria.
    sort_field / sort_direction: first-class sort params. Take precedence
    over filter_criteria.filters.sort_by. Defaults: deal_score DESC.
    page / page_size: pagination. Defaults: page=1, page_size=25.
    """
    county_fips: list[str]
    filter_criteria: dict
    rehab_cost_per_sqft: float = 22.00
    min_comp_sales_for_arv: int = 3
    comp_radius_miles: float = 1.0
    comp_year_built_tolerance: int = 15
    deal_score_weights: dict = {}
    sort_field: str = "deal_score"
    sort_direction: str = "DESC"
    page: int = 1
    page_size: int = 25


# ── Filter application ───────────────────────────────────────────────────

def _apply_filters(
    stmt,
    filters: dict[str, Any],
):
    """Apply filter_criteria dimensions as WHERE clauses.

    Only non-null filter values are applied. Null values mean the
    dimension is unconstrained — no WHERE clause added.
    Returns the augmented select statement.
    """
    f = filters

    # just_value
    jv = f.get("just_value", {})
    if jv.get("min") is not None:
        stmt = stmt.where(Property.jv >= jv["min"])
    if jv.get("max") is not None:
        stmt = stmt.where(Property.jv <= jv["max"])

    # list_price
    lp = f.get("list_price", {})
    if lp.get("min") is not None:
        stmt = stmt.where(Property.list_price >= lp["min"])
    if lp.get("max") is not None:
        stmt = stmt.where(Property.list_price <= lp["max"])

    # list_price_to_jv_ratio
    lpjr = f.get("list_price_to_jv_ratio", {})
    if lpjr.get("min") is not None:
        stmt = stmt.where(
            Property.list_price.isnot(None),
            Property.jv.isnot(None),
            Property.jv > 0,
            (Property.list_price / Property.jv) >= lpjr["min"],
        )
    if lpjr.get("max") is not None:
        stmt = stmt.where(
            Property.list_price.isnot(None),
            Property.jv.isnot(None),
            Property.jv > 0,
            (Property.list_price / Property.jv) <= lpjr["max"],
        )

    # year_built (act_yr_blt)
    yb = f.get("year_built", {})
    if yb.get("min") is not None:
        stmt = stmt.where(Property.act_yr_blt >= yb["min"])
    if yb.get("max") is not None:
        stmt = stmt.where(Property.act_yr_blt <= yb["max"])

    # effective_year_built (eff_yr_blt)
    eyb = f.get("effective_year_built", {})
    if eyb.get("min") is not None:
        stmt = stmt.where(Property.eff_yr_blt >= eyb["min"])
    if eyb.get("max") is not None:
        stmt = stmt.where(Property.eff_yr_blt <= eyb["max"])

    # living_area_sqft (tot_lvg_area)
    la = f.get("living_area_sqft", {})
    if la.get("min") is not None:
        stmt = stmt.where(Property.tot_lvg_area >= la["min"])
    if la.get("max") is not None:
        stmt = stmt.where(Property.tot_lvg_area <= la["max"])

    # lot_sqft (lnd_sqfoot)
    ls = f.get("lot_sqft", {})
    if ls.get("min") is not None:
        stmt = stmt.where(Property.lnd_sqfoot >= ls["min"])
    if ls.get("max") is not None:
        stmt = stmt.where(Property.lnd_sqfoot <= ls["max"])

    # bedrooms
    bed = f.get("bedrooms", {})
    if bed.get("exact") is not None:
        stmt = stmt.where(Property.bedrooms == bed["exact"])
    else:
        if bed.get("min") is not None:
            stmt = stmt.where(Property.bedrooms >= bed["min"])
        if bed.get("max") is not None:
            stmt = stmt.where(Property.bedrooms <= bed["max"])

    # bathrooms
    bath = f.get("bathrooms", {})
    if bath.get("exact") is not None:
        stmt = stmt.where(Property.bathrooms == bath["exact"])
    else:
        if bath.get("min") is not None:
            stmt = stmt.where(Property.bathrooms >= bath["min"])
        if bath.get("max") is not None:
            stmt = stmt.where(Property.bathrooms <= bath["max"])

    # imp_qual
    iq = f.get("imp_qual", {})
    if iq.get("min") is not None:
        stmt = stmt.where(Property.imp_qual >= iq["min"])
    if iq.get("max") is not None:
        stmt = stmt.where(Property.imp_qual <= iq["max"])

    # num_buildings (no_buldng)
    nb = f.get("num_buildings", {})
    if nb.get("max") is not None:
        stmt = stmt.where(Property.no_buldng <= nb["max"])

    # num_residential_units (no_res_unts)
    nru = f.get("num_residential_units", {})
    if nru.get("max") is not None:
        stmt = stmt.where(Property.no_res_unts <= nru["max"])

    # assessed_value (av_nsd)
    av = f.get("assessed_value", {})
    if av.get("min") is not None:
        stmt = stmt.where(Property.av_nsd >= av["min"])
    if av.get("max") is not None:
        stmt = stmt.where(Property.av_nsd <= av["max"])

    # land_value (lnd_val)
    lv = f.get("land_value", {})
    if lv.get("min") is not None:
        stmt = stmt.where(Property.lnd_val >= lv["min"])
    if lv.get("max") is not None:
        stmt = stmt.where(Property.lnd_val <= lv["max"])

    # nav_total_assessment
    nav = f.get("nav_total_assessment", {})
    if nav.get("max") is not None:
        stmt = stmt.where(Property.nav_total_assessment <= nav["max"])

    # special_feature_value (spec_feat_val)
    sfv = f.get("special_feature_value", {})
    if sfv.get("max") is not None:
        stmt = stmt.where(Property.spec_feat_val <= sfv["max"])

    # years_since_last_sale
    ysls = f.get("years_since_last_sale", {})
    if ysls.get("min") is not None:
        stmt = stmt.where(Property.years_since_last_sale >= ysls["min"])
    if ysls.get("max") is not None:
        stmt = stmt.where(Property.years_since_last_sale <= ysls["max"])

    # soh_compression_ratio
    soh = f.get("soh_compression_ratio", {})
    if soh.get("min") is not None:
        stmt = stmt.where(Property.soh_compression_ratio >= soh["min"])
    if soh.get("max") is not None:
        stmt = stmt.where(Property.soh_compression_ratio <= soh["max"])

    # improvement_to_land_ratio
    ilr = f.get("improvement_to_land_ratio", {})
    if ilr.get("min") is not None:
        stmt = stmt.where(Property.improvement_to_land_ratio >= ilr["min"])
    if ilr.get("max") is not None:
        stmt = stmt.where(Property.improvement_to_land_ratio <= ilr["max"])

    # absentee_owner
    ao = f.get("absentee_owner", {})
    if ao.get("required") is not None:
        stmt = stmt.where(Property.absentee_owner.is_(ao["required"]))

    # homestead_status — homestead = exmpt_01 > 0
    hs = f.get("homestead_status", {})
    if hs.get("required") is True:
        stmt = stmt.where(Property.exmpt_01 > 0)
    elif hs.get("required") is False:
        stmt = stmt.where(
            (Property.exmpt_01.is_(None)) | (Property.exmpt_01 == 0)
        )

    # owner_state_dom (exclude list)
    osd = f.get("owner_state_dom", {})
    if osd.get("exclude"):
        stmt = stmt.where(Property.own_state_dom.notin_(osd["exclude"]))

    # dor_use_code (include list) — stored as zero-padded 3-digit strings
    duc = f.get("dor_use_code", {})
    if duc.get("include"):
        padded = [str(v).zfill(3) for v in duc["include"]]
        stmt = stmt.where(Property.dor_uc.in_(padded))

    # zip_codes (include list)
    zc = f.get("zip_codes", {})
    if zc.get("include"):
        stmt = stmt.where(Property.phy_zipcd.in_(zc["include"]))

    # mkt_ar_codes (include list)
    mac = f.get("mkt_ar_codes", {})
    if mac.get("include"):
        stmt = stmt.where(Property.mkt_ar.in_(mac["include"]))

    # nbrhd_codes (include list)
    nc = f.get("nbrhd_codes", {})
    if nc.get("include"):
        stmt = stmt.where(Property.nbrhd_cd.in_(nc["include"]))

    # census_block_groups (include list)
    cbg = f.get("census_block_groups", {})
    if cbg.get("include"):
        stmt = stmt.where(Property.census_bk.in_(cbg["include"]))

    # ext_wall_codes (include list)
    ewc = f.get("ext_wall_codes", {})
    if ewc.get("include"):
        stmt = stmt.where(Property.exterior_wall.in_(ewc["include"]))

    # foundation_codes (include list)
    fc = f.get("foundation_codes", {})
    if fc.get("include"):
        stmt = stmt.where(Property.foundation_type.in_(fc["include"]))

    # prior_sale_qualification (include list — qual_cd1)
    psq = f.get("prior_sale_qualification", {})
    if psq.get("include"):
        stmt = stmt.where(Property.qual_cd1.in_(psq["include"]))

    # par_split_recent — par_splt IS NOT NULL and non-empty
    psr = f.get("par_split_recent", {})
    if psr.get("required") is True:
        stmt = stmt.where(
            Property.par_splt.isnot(None),
            Property.par_splt != "",
        )

    # min_arv_spread — arv_spread >= value
    mas = f.get("min_arv_spread", {})
    if mas.get("value") is not None:
        stmt = stmt.where(Property.arv_spread >= mas["value"])

    return stmt


# ── Deal score computation ───────────────────────────────────────────────

def _compute_deal_score(
    row: _ScoringRow,
    ev: _EventScoringRow | None,
    weights: dict[str, Any],
) -> float | None:
    """Compute a normalised deal score in [0.0, 1.0] at query time.

    Operates on lightweight _ScoringRow and _EventScoringRow tuples —
    not full ORM objects. Returns None if no weights configured or
    required values missing.

    Dimensions:
        arv_spread_score  — arv_spread relative to jv
        signal_tier_score — inverted signal_tier (1=best)
        dom_score         — days_on_market (lower = more motivated)
        absentee_score    — absentee_owner boolean bonus
    """
    if not weights:
        return None

    score = 0.0
    total_weight = 0.0

    w = weights.get("arv_spread_score", 0.0)
    if w and row.arv_spread is not None and row.jv:
        normalised = min(row.arv_spread / row.jv, 1.0)
        score += w * max(normalised, 0.0)
        total_weight += w

    w = weights.get("signal_tier_score", 0.0)
    if w and ev and ev.signal_tier is not None:
        tier_map = {1: 1.0, 2: 0.66, 3: 0.33}
        normalised = tier_map.get(ev.signal_tier, 0.0)
        score += w * normalised
        total_weight += w

    w = weights.get("dom_score", 0.0)
    if w and ev and ev.days_on_market is not None:
        normalised = 1.0 - min(ev.days_on_market / 365, 1.0)
        score += w * normalised
        total_weight += w

    w = weights.get("absentee_score", 0.0)
    if w and row.absentee_owner:
        score += w * 1.0
        total_weight += w

    if total_weight == 0.0:
        return None

    return round(score / total_weight, 4)


# ── Core search logic — shared by both routes ────────────────────────────

async def _execute_search(
    profile_counties: list[str],
    filters: dict[str, Any],
    weights: dict[str, Any],
    page: int,
    page_size: int,
    sort_field: str,
    sort_direction: str,
    db: AsyncSession,
) -> PaginatedPropertySearchResult:
    """Option C hybrid search.

    Step 1: SQL — fetch scoring columns only for all filtered parcels.
    Step 2: SQL — fetch latest listing_event scoring columns for those parcels.
    Step 3: Python — apply event-dependent filters, score, sort full ID list.
    Step 4: SQL — fetch full Property ORM objects for page slice only.
    Step 5: SQL — fetch full ListingEvent ORM objects for page slice only.
    Step 6: Python — build response objects.
    """

    # ── Step 1: lightweight property scoring fetch ────────────────────
    scoring_stmt = (
        select(
            Property.county_fips,
            Property.parcel_id,
            Property.arv_spread,
            Property.jv,
            Property.absentee_owner,
            Property.list_price,
            Property.years_since_last_sale,
            Property.tot_lvg_area,
            Property.act_yr_blt,
            Property.phy_addr1,
        )
        .order_by(Property.county_fips, Property.parcel_id)
    )
    scoring_stmt = scoring_stmt.where(Property.county_fips.in_(profile_counties))
    scoring_stmt = _apply_filters(scoring_stmt, filters)

    scoring_result = await db.execute(scoring_stmt)
    scoring_rows: list[_ScoringRow] = [
        _ScoringRow(*row) for row in scoring_result.all()
    ]

    if not scoring_rows:
        return PaginatedPropertySearchResult(
            total=0, page=page, page_size=page_size, total_pages=1, results=[]
        )

    # ── Step 2: lightweight event scoring fetch ───────────────────────
    # Fetch the latest event per parcel using a subquery on max(id).
    # Only fetches columns needed for scoring and event-dependent filters.
    parcel_key_set = {(r.county_fips, r.parcel_id) for r in scoring_rows}

    ev_subq = (
        select(
            ListingEvent.county_fips,
            ListingEvent.parcel_id,
            func.max(ListingEvent.id).label("max_id"),
        )
        .where(ListingEvent.county_fips.in_(profile_counties))
        .group_by(ListingEvent.county_fips, ListingEvent.parcel_id)
        .subquery()
    )

    ev_scoring_stmt = (
        select(
            ListingEvent.county_fips,
            ListingEvent.parcel_id,
            ListingEvent.signal_tier,
            ListingEvent.days_on_market,
            ListingEvent.listing_type,
            ListingEvent.arv_estimate,
            ListingEvent.arv_source,
            ListingEvent.arv_spread,
        )
        .join(
            ev_subq,
            (ListingEvent.county_fips == ev_subq.c.county_fips)
            & (ListingEvent.parcel_id == ev_subq.c.parcel_id)
            & (ListingEvent.id == ev_subq.c.max_id),
        )
    )

    ev_scoring_result = await db.execute(ev_scoring_stmt)
    event_scoring_map: dict[tuple[str, str], _EventScoringRow] = {}
    for row in ev_scoring_result.all():
        key = (row.county_fips, row.parcel_id)
        if key in parcel_key_set:
            event_scoring_map[key] = _EventScoringRow(*row)

    # ── Step 3: event-dependent filters, scoring, sorting ────────────

    # listing_type filter — requires event
    lt = filters.get("listing_types", {})
    if lt.get("include"):
        allowed = set(lt["include"])
        scoring_rows = [
            r for r in scoring_rows
            if (ev := event_scoring_map.get((r.county_fips, r.parcel_id))) is not None
            and ev.listing_type in allowed
        ]

    # days_on_market filter — requires event
    dom = filters.get("days_on_market", {})
    if dom.get("min") is not None or dom.get("max") is not None:
        filtered = []
        for r in scoring_rows:
            ev = event_scoring_map.get((r.county_fips, r.parcel_id))
            if ev is None:
                continue
            if dom.get("min") is not None and (
                ev.days_on_market is None or ev.days_on_market < dom["min"]
            ):
                continue
            if dom.get("max") is not None and (
                ev.days_on_market is None or ev.days_on_market > dom["max"]
            ):
                continue
            filtered.append(r)
        scoring_rows = filtered

    # Score and apply min_deal_score filter
    min_ds = filters.get("min_deal_score", {})
    min_deal_score_val = min_ds.get("value") if min_ds else None

    scored: list[tuple[_ScoringRow, _EventScoringRow | None, float | None]] = []
    for r in scoring_rows:
        ev = event_scoring_map.get((r.county_fips, r.parcel_id))
        ds = _compute_deal_score(r, ev, weights)
        if min_deal_score_val is not None and (ds is None or ds < min_deal_score_val):
            continue
        scored.append((r, ev, ds))

    # Sort
    supported_sort_fields = {
        "deal_score", "arv_spread", "arv_source", "list_price", "jv",
        "years_since_last_sale", "tot_lvg_area", "act_yr_blt",
        "address", "signal_tier",
    }
    sort_direction = str(sort_direction).upper()
    reverse = sort_direction != "ASC"
    if sort_field not in supported_sort_fields:
        sort_field = "deal_score"
        reverse = True

    def _sort_key(
        item: tuple[_ScoringRow, _EventScoringRow | None, float | None]
    ):
        row, ev, ds = item
        tb = row.parcel_id

        if sort_field == "deal_score":
            return (ds if ds is not None else -1.0,
                    row.arv_spread if row.arv_spread is not None else -1,
                    tb)
        if sort_field == "arv_spread":
            return (row.arv_spread if row.arv_spread is not None else -1,
                    ds if ds is not None else -1.0,
                    tb)
        if sort_field == "jv":
            return (row.jv if row.jv is not None else -1,
                    ds if ds is not None else -1.0,
                    tb)
        if sort_field == "list_price":
            return (row.list_price if row.list_price is not None else -1,
                    ds if ds is not None else -1.0,
                    tb)
        if sort_field == "years_since_last_sale":
            return (row.years_since_last_sale if row.years_since_last_sale is not None else -1,
                    ds if ds is not None else -1.0,
                    tb)
        if sort_field == "tot_lvg_area":
            return (row.tot_lvg_area if row.tot_lvg_area is not None else -1,
                    ds if ds is not None else -1.0,
                    tb)
        if sort_field == "act_yr_blt":
            return (row.act_yr_blt if row.act_yr_blt is not None else -1,
                    ds if ds is not None else -1.0,
                    tb)
        if sort_field == "address":
            return (row.phy_addr1 if row.phy_addr1 is not None else "",
                    tb)
        if sort_field == "arv_source":
            return (ev.arv_source if ev and ev.arv_source is not None else "",
                    tb)
        if sort_field == "signal_tier":
            return (ev.signal_tier if ev and ev.signal_tier is not None else 99,
                    ds if ds is not None else -1.0,
                    tb)
        return (ds if ds is not None else -1.0,
                row.arv_spread if row.arv_spread is not None else -1,
                tb)

    scored.sort(key=_sort_key, reverse=reverse)

    # max_results cap — applied after sort so the cap takes the
    # top-N rows by the requested sort field, not by database order.
    max_res = filters.get("max_results", {})
    limit = max_res.get("value") if max_res else None
    if limit:
        scored = scored[:limit]

    total = len(scored)
    total_pages = max(1, -(-total // page_size))

    # Page slice — IDs only
    start = (page - 1) * page_size
    end = start + page_size
    page_slice = scored[start:end]

    if not page_slice:
        return PaginatedPropertySearchResult(
            total=total, page=page, page_size=page_size,
            total_pages=total_pages, results=[],
        )

    # ── Step 4: full Property fetch for page slice only ───────────────
    # Preserve page order — fetch then re-sort by the scored order.
    page_keys = [(r.county_fips, r.parcel_id) for r, _, _ in page_slice]

    # County-scoped fetches to avoid tuple_ IN StatementTooComplexError
    # (item 78). Group keys by county, fetch per county, merge.
    keys_by_county: dict[str, list[str]] = defaultdict(list)
    for fips, pid in page_keys:
        keys_by_county[fips].append(pid)

    prop_map: dict[tuple[str, str], Property] = {}
    for fips, pids in keys_by_county.items():
        prop_result = await db.execute(
            select(Property).where(
                Property.county_fips == fips,
                Property.parcel_id.in_(pids),
            )
        )
        for prop in prop_result.scalars().all():
            prop_map[(prop.county_fips, prop.parcel_id)] = prop

    # ── Step 5: full ListingEvent fetch for page slice only ───────────
    ev_map: dict[tuple[str, str], ListingEvent] = {}
    for fips, pids in keys_by_county.items():
        ev_full_result = await db.execute(
            select(ListingEvent)
            .where(
                ListingEvent.county_fips == fips,
                ListingEvent.parcel_id.in_(pids),
            )
            .order_by(ListingEvent.parcel_id, ListingEvent.id.desc())
        )
        for ev in ev_full_result.scalars().all():
            key = (ev.county_fips, ev.parcel_id)
            if key not in ev_map:
                ev_map[key] = ev

    # ── Step 6: build response — preserve scored sort order ──────────
    out: list[PropertySearchResult] = []
    for scoring_row, ev_scoring, ds in page_slice:
        key = (scoring_row.county_fips, scoring_row.parcel_id)
        prop = prop_map.get(key)
        if prop is None:
            # Should not happen — parcel passed filter so it exists.
            # Skip defensively rather than crash.
            continue

        ev_full = ev_map.get(key)
        latest = ListingEventSummary.model_validate(ev_full) if ev_full else None
        arv_source = ev_full.arv_source if ev_full else None
        arv_estimate = (ev_full.arv_estimate if ev_full else None) or prop.arv_estimate

        out.append(
            PropertySearchResult(
                county_fips=prop.county_fips,
                parcel_id=prop.parcel_id,
                phy_addr1=prop.phy_addr1,
                phy_city=prop.phy_city,
                phy_zipcd=prop.phy_zipcd,
                dor_uc=prop.dor_uc,
                jv=prop.jv,
                tot_lvg_area=prop.tot_lvg_area,
                lnd_sqfoot=prop.lnd_sqfoot,
                act_yr_blt=prop.act_yr_blt,
                eff_yr_blt=prop.eff_yr_blt,
                bedrooms=prop.bedrooms,
                bathrooms=float(prop.bathrooms) if prop.bathrooms is not None else None,
                absentee_owner=prop.absentee_owner,
                imp_qual=prop.imp_qual,
                years_since_last_sale=prop.years_since_last_sale,
                improvement_to_land_ratio=float(prop.improvement_to_land_ratio) if prop.improvement_to_land_ratio is not None else None,
                soh_compression_ratio=float(prop.soh_compression_ratio) if prop.soh_compression_ratio is not None else None,
                arv_estimate=arv_estimate,
                arv_spread=prop.arv_spread,
                jv_per_sqft=float(prop.jv_per_sqft) if prop.jv_per_sqft is not None else None,
                deal_score=ds,
                arv_source=arv_source,
                latitude=float(prop.latitude) if prop.latitude is not None else None,
                longitude=float(prop.longitude) if prop.longitude is not None else None,
                latest_listing=latest,
            )
        )

    return PaginatedPropertySearchResult(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        results=out,
    )


# ── Routes ───────────────────────────────────────────────────────────────

@router.get("/properties", response_model=PaginatedPropertySearchResult)
async def search_properties(
    filter_profile_id: int = Query(..., description="ID of the filter profile to execute"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(25, ge=1, le=500, description="Results per page"),
    sort_field: str = Query("deal_score", description="Field to sort by"),
    sort_direction: str = Query("DESC", description="ASC or DESC"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedPropertySearchResult:
    """Execute a live multi-county property search using the specified filter profile.

    Loads the profile, validates county access, applies filter_criteria at
    query time, scores, sorts, and returns one page of results.

    Uses Option C hybrid architecture — lightweight scoring fetch across
    all filtered rows, full ORM hydration for page slice only.

    max_results from filter_criteria is applied before pagination.
    user_profile_prefs is upserted with the total result count (pre-page).
    """
    profile = await _get_visible_active_profile(filter_profile_id, current_user, db)

    profile_counties = list(dict.fromkeys(profile.county_fips))
    if not profile_counties:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Filter profile {filter_profile_id} has no counties configured",
        )

    filters: dict[str, Any] = profile.filter_criteria.get("filters", {})
    weights: dict[str, Any] = profile.deal_score_weights or {}

    paginated = await _execute_search(
        profile_counties, filters, weights, page, page_size,
        sort_field, sort_direction, db
    )

    # Upsert user_profile_prefs — total count, not page count
    await db.execute(
        pg_insert(UserProfilePrefs)
        .values(
            user_id=current_user.id,
            profile_id=filter_profile_id,
            last_searched_at=func.now(),
            last_result_count=paginated.total,
            run_count=1,
        )
        .on_conflict_do_update(
            index_elements=["user_id", "profile_id"],
            set_={
                "last_searched_at": func.now(),
                "last_result_count": paginated.total,
                "run_count": UserProfilePrefs.run_count + 1,
                "updated_at": func.now(),
            },
        )
    )
    await db.commit()

    return paginated


@router.post("/properties/search", response_model=PaginatedPropertySearchResult)
async def search_properties_inline(
    body: InlineSearchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedPropertySearchResult:
    """Execute a live multi-county property search from inline filter criteria.

    No filter profile is required and none is written. County access is
    validated. Behaviour is otherwise identical to search_properties.
    user_profile_prefs is not written — no profile_id is available.

    Uses Option C hybrid architecture — lightweight scoring fetch across
    all filtered rows, full ORM hydration for page slice only.
    """
    profile_counties = list(dict.fromkeys(body.county_fips))
    if not profile_counties:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="county_fips must contain at least one county",
        )

    if not current_user.is_superuser:
        accessible = await _get_accessible_fips(current_user, db)
        _assert_county_access(profile_counties, accessible, is_superuser=False)

    filters: dict[str, Any] = body.filter_criteria.get("filters", {})
    weights: dict[str, Any] = body.deal_score_weights or {}

    return await _execute_search(
        profile_counties, filters, weights, body.page, body.page_size,
        body.sort_field, body.sort_direction, db
    )


@router.get("/{county_fips}/properties/{parcel_id}", response_model=PropertyDetail)
async def get_property(
    county_fips: str = Depends(county_access()),
    parcel_id: str = Path(..., description="16-character alphanumeric parcel ID"),
    db: AsyncSession = Depends(get_db),
) -> PropertyDetail:
    """Return full property detail for a single parcel.

    Includes the most recent listing_event if one exists.
    """
    result = await db.execute(
        select(Property).where(
            Property.county_fips == county_fips,
            Property.parcel_id == parcel_id,
        )
    )
    prop: Property | None = result.scalar_one_or_none()

    if prop is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Property {parcel_id} not found in county {county_fips}",
        )

    ev_result = await db.execute(
        select(ListingEvent)
        .where(
            ListingEvent.county_fips == county_fips,
            ListingEvent.parcel_id == parcel_id,
        )
        .order_by(ListingEvent.id.desc())
        .limit(1)
    )
    ev: ListingEvent | None = ev_result.scalar_one_or_none()
    latest = ListingEventSummary.model_validate(ev) if ev else None

    return PropertyDetail(
        county_fips=prop.county_fips,
        parcel_id=prop.parcel_id,
        state_par_id=prop.state_par_id,
        phy_addr1=prop.phy_addr1,
        phy_city=prop.phy_city,
        phy_zipcd=prop.phy_zipcd,
        own_name=prop.own_name,
        own_addr1=prop.own_addr1,
        own_city=prop.own_city,
        own_state=prop.own_state,
        own_zipcd=prop.own_zipcd,
        absentee_owner=prop.absentee_owner,
        dor_uc=prop.dor_uc,
        pa_uc=prop.pa_uc,
        jv=prop.jv,
        av_nsd=prop.av_nsd,
        lnd_val=prop.lnd_val,
        nav_total_assessment=float(prop.nav_total_assessment) if prop.nav_total_assessment is not None else None,
        tot_lvg_area=prop.tot_lvg_area,
        lnd_sqfoot=prop.lnd_sqfoot,
        act_yr_blt=prop.act_yr_blt,
        eff_yr_blt=prop.eff_yr_blt,
        const_class=prop.const_class,
        imp_qual=prop.imp_qual,
        bedrooms=prop.bedrooms,
        bathrooms=float(prop.bathrooms) if prop.bathrooms is not None else None,
        foundation_type=prop.foundation_type,
        exterior_wall=prop.exterior_wall,
        roof_type=prop.roof_type,
        cama_quality_code=prop.cama_quality_code,
        cama_condition_code=prop.cama_condition_code,
        no_buldng=prop.no_buldng,
        no_res_unts=prop.no_res_unts,
        mkt_ar=prop.mkt_ar,
        nbrhd_cd=prop.nbrhd_cd,
        census_bk=prop.census_bk,
        zoning=prop.zoning,
        years_since_last_sale=prop.years_since_last_sale,
        improvement_to_land_ratio=float(prop.improvement_to_land_ratio) if prop.improvement_to_land_ratio is not None else None,
        soh_compression_ratio=float(prop.soh_compression_ratio) if prop.soh_compression_ratio is not None else None,
        spec_feat_val=prop.spec_feat_val,
        jv_per_sqft=float(prop.jv_per_sqft) if prop.jv_per_sqft is not None else None,
        arv_estimate=prop.arv_estimate,
        arv_spread=prop.arv_spread,
        qual_cd1=prop.qual_cd1,
        sale_prc1=prop.sale_prc1,
        sale_yr1=prop.sale_yr1,
        sale_mo1=prop.sale_mo1,
        qual_cd2=prop.qual_cd2,
        sale_prc2=prop.sale_prc2,
        sale_yr2=prop.sale_yr2,
        sale_mo2=prop.sale_mo2,
        latitude=float(prop.latitude) if prop.latitude is not None else None,
        longitude=float(prop.longitude) if prop.longitude is not None else None,
        nal_ingested_at=prop.nal_ingested_at,
        cama_enriched_at=prop.cama_enriched_at,
        latest_listing=latest,
    )
