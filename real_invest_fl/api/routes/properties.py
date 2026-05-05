"""
Properties routes — core search and single-parcel detail.

GET /{county_fips}/properties
    Loads the specified filter profile, builds a query-time WHERE clause
    from filter_criteria, computes deal score, returns results ranked by
    deal score descending.

GET /{county_fips}/properties/{parcel_id}
    Returns full property detail for a single parcel, including the most
    recent listing_event if one exists.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from real_invest_fl.api.deps import county_access, get_db
from real_invest_fl.db.models.filter_profile import FilterProfile
from real_invest_fl.db.models.listing_event import ListingEvent
from real_invest_fl.db.models.property import Property

router = APIRouter(prefix="/{county_fips}/properties", tags=["properties"])


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
    latest_listing: ListingEventSummary | None

    model_config = {"from_attributes": True}


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


# ── Filter application ───────────────────────────────────────────────────

def _apply_filters(
    stmt,
    filters: dict[str, Any],
) :
    """Apply filter_criteria filter dimensions as WHERE clauses.

    Only non-null filter values are applied. Null values in the criteria
    document mean the dimension is unconstrained — no WHERE clause added.
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

    # county_nos (include list — dor co_no integer)
    cn = f.get("county_nos", {})
    if cn.get("include"):
        stmt = stmt.where(Property.co_no.in_(cn["include"]))

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
    prop: Property,
    latest_event: ListingEvent | None,
    weights: dict[str, Any],
) -> float | None:
    """Compute a normalised deal score in [0.0, 1.0] at query time.

    Scoring dimensions and their weights are drawn from
    filter_profile.deal_score_weights. Returns None if no weights are
    configured or if required values are missing.

    Current dimensions:
        arv_spread_score  — arv_spread relative to jv
        signal_tier_score — inverted signal_tier (1=best)
        dom_score         — days_on_market (lower = more motivated)
        absentee_score    — absentee_owner boolean bonus

    All dimensions are normalised to [0, 1] before weighting.
    Total weight need not sum to 1 — output is normalised by total weight.
    """
    if not weights:
        return None

    score = 0.0
    total_weight = 0.0

    # arv_spread_score
    w = weights.get("arv_spread_score", 0.0)
    if w and prop.arv_spread is not None and prop.jv:
        normalised = min(prop.arv_spread / prop.jv, 1.0)
        score += w * max(normalised, 0.0)
        total_weight += w

    # signal_tier_score — tier 1 = 1.0, tier 2 = 0.66, tier 3 = 0.33
    w = weights.get("signal_tier_score", 0.0)
    if w and latest_event and latest_event.signal_tier is not None:
        tier_map = {1: 1.0, 2: 0.66, 3: 0.33}
        normalised = tier_map.get(latest_event.signal_tier, 0.0)
        score += w * normalised
        total_weight += w

    # dom_score — cap at 365 days, invert so 0 DOM = 1.0
    w = weights.get("dom_score", 0.0)
    if w and latest_event and latest_event.days_on_market is not None:
        normalised = 1.0 - min(latest_event.days_on_market / 365, 1.0)
        score += w * normalised
        total_weight += w

    # absentee_score — binary bonus
    w = weights.get("absentee_score", 0.0)
    if w and prop.absentee_owner:
        score += w * 1.0
        total_weight += w

    if total_weight == 0.0:
        return None

    return round(score / total_weight, 4)


# ── Routes ───────────────────────────────────────────────────────────────

@router.get("", response_model=list[PropertySearchResult])
async def search_properties(
    county_fips: str = Depends(county_access()),
    filter_profile_id: int = Query(..., description="ID of the filter profile to execute"),
    db: AsyncSession = Depends(get_db),
) -> list[PropertySearchResult]:
    """Execute a live query against properties using the specified filter profile.

    Applies filter_criteria as WHERE clauses at query time.
    Computes deal score at query time using deal_score_weights.
    Returns results ranked by deal score descending, then arv_spread descending.
    ARV source distinction (COMP vs JV_FALLBACK) is surfaced in each result.
    max_results from filter_criteria is honoured if set.
    """
    # Load and validate the filter profile
    fp_result = await db.execute(
        select(FilterProfile).where(
            FilterProfile.id == filter_profile_id,
            FilterProfile.county_fips == county_fips,
            FilterProfile.is_active.is_(True),
        )
    )
    profile: FilterProfile | None = fp_result.scalar_one_or_none()

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Filter profile {filter_profile_id} not found for county {county_fips}",
        )

    filters: dict[str, Any] = profile.filter_criteria.get("filters", {})
    weights: dict[str, Any] = profile.deal_score_weights or {}

    # Base query — county scoped
    stmt = select(Property).where(Property.county_fips == county_fips)

    # Apply filter dimensions
    stmt = _apply_filters(stmt, filters)

    # max_results
    max_res = filters.get("max_results", {})
    limit = max_res.get("value") if max_res else None

    # Fetch properties
    result = await db.execute(stmt)
    properties = result.scalars().all()

    # For each property fetch latest listing_event
    parcel_ids = [p.parcel_id for p in properties]
    latest_events: dict[str, ListingEvent] = {}

    if parcel_ids:
        # Subquery: max id per parcel within county — id is append-only autoincrement
        sub = (
            select(
                ListingEvent.parcel_id,
                ListingEvent.id,
            )
            .where(
                ListingEvent.county_fips == county_fips,
                ListingEvent.parcel_id.in_(parcel_ids),
            )
            .distinct(ListingEvent.parcel_id)
            .order_by(ListingEvent.parcel_id, ListingEvent.id.desc())
            .subquery()
        )
        ev_result = await db.execute(
            select(ListingEvent).join(sub, ListingEvent.id == sub.c.id)
        )
        for ev in ev_result.scalars().all():
            latest_events[ev.parcel_id] = ev

    # Apply listing_type filter if set — post-fetch against latest event
    lt = filters.get("listing_types", {})
    if lt.get("include"):
        allowed = set(lt["include"])
        properties = [
            p for p in properties
            if latest_events.get(p.parcel_id) is not None
            and latest_events[p.parcel_id].listing_type in allowed
        ]

    # Apply days_on_market filter — lives on listing_event, not property
    dom = filters.get("days_on_market", {})
    if dom.get("min") is not None or dom.get("max") is not None:
        filtered = []
        for p in properties:
            ev = latest_events.get(p.parcel_id)
            if ev is None:
                continue
            if dom.get("min") is not None and (ev.days_on_market is None or ev.days_on_market < dom["min"]):
                continue
            if dom.get("max") is not None and (ev.days_on_market is None or ev.days_on_market > dom["max"]):
                continue
            filtered.append(p)
        properties = filtered

    # Apply min_deal_score filter — computed, not stored
    min_ds = filters.get("min_deal_score", {})
    min_deal_score_val = min_ds.get("value") if min_ds else None

    # Compute deal scores
    scored: list[tuple[Property, ListingEvent | None, float | None]] = []
    for p in properties:
        ev = latest_events.get(p.parcel_id)
        ds = _compute_deal_score(p, ev, weights)
        if min_deal_score_val is not None and (ds is None or ds < min_deal_score_val):
            continue
        scored.append((p, ev, ds))

    # Sort — deal_score desc, arv_spread desc as tiebreaker
    scored.sort(
        key=lambda x: (
            x[2] if x[2] is not None else -1.0,
            x[0].arv_spread if x[0].arv_spread is not None else -1,
        ),
        reverse=True,
    )

    # Apply max_results
    if limit:
        scored = scored[:limit]

    # Build response
    out: list[PropertySearchResult] = []
    for prop, ev, ds in scored:
        latest = ListingEventSummary.model_validate(ev) if ev else None
        arv_source = ev.arv_source if ev else None
        arv_estimate = ev.arv_estimate if ev else None

        out.append(PropertySearchResult(
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
            latest_listing=latest,
        ))

    return out


@router.get("/{parcel_id}", response_model=PropertyDetail)
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

    # Latest listing event
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
