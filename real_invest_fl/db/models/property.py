"""
Property — Master Qualified Inventory (MQI).
Primary key is (county_fips, parcel_id) — composite, county-scoped.
NAL fields use DOR field names directly. CAMA fields populated in Stage 2.
Phase 2 fields (seller_probability_score, permit_count) are nullable
and will remain NULL until their respective pipeline stages are built.
"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import (
    String, Integer, Boolean, DateTime,
    Numeric, UniqueConstraint, Index, func
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geometry
from real_invest_fl.db.base import Base


class Property(Base):
    __tablename__ = "properties"
    __table_args__ = (
        UniqueConstraint("county_fips", "parcel_id", name="uq_county_parcel"),
        Index("ix_properties_county_fips",  "county_fips"),
        Index("ix_properties_dor_uc",       "dor_uc"),
        Index("ix_properties_const_class",  "const_class"),
        Index("ix_properties_act_yr_blt",   "act_yr_blt"),
        Index("ix_properties_mqi_qualified", "mqi_qualified"),
        Index("ix_properties_phy_zipcd",    "phy_zipcd"),
        Index("ix_properties_state_par_id", "state_par_id"),
        Index("ix_properties_jv",           "jv"),
        Index("ix_properties_sale_yr1",     "sale_yr1"),
        Index("ix_properties_mkt_ar",       "mkt_ar"),
        Index("ix_properties_census_bk",    "census_bk"),
    )

    # ------------------------------------------------------------------ #
    # Primary key                                                          #
    # ------------------------------------------------------------------ #
    county_fips: Mapped[str] = mapped_column(String(5), primary_key=True)
    parcel_id:   Mapped[str] = mapped_column(String(30), primary_key=True)

    # STATE_PAR_ID — DOR-assigned statewide uniform parcel identifier.
    # Replaces parcel_id_normalized. Used as cross-county join key.
    state_par_id: Mapped[str | None] = mapped_column(String(18))

    # ------------------------------------------------------------------ #
    # NAL — Parcel identification and classification                       #
    # ------------------------------------------------------------------ #
    co_no:    Mapped[int | None] = mapped_column(Integer)   # CO_NO field 1
    asmnt_yr: Mapped[int | None] = mapped_column(Integer)   # ASMNT_YR field 4
    dor_uc:   Mapped[str | None] = mapped_column(String(10))  # DOR_UC field 8
    pa_uc:    Mapped[str | None] = mapped_column(String(10))  # PA_UC field 9

    # ------------------------------------------------------------------ #
    # NAL — Value fields                                                   #
    # ------------------------------------------------------------------ #
    jv:      Mapped[int | None] = mapped_column(Integer)  # JV field 11 — Just Value
    av_nsd:  Mapped[int | None] = mapped_column(Integer)  # AV_NSD field 15 — Non-school assessed value
    tv_nsd:  Mapped[int | None] = mapped_column(Integer)  # TV_NSD field 17 — Non-school taxable value
    av_sd:   Mapped[int | None] = mapped_column(Integer)  # AV_SD field 14 — School assessed value
    tv_sd:   Mapped[int | None] = mapped_column(Integer)  # TV_SD field 16 — School taxable value
    jv_hmstd: Mapped[int | None] = mapped_column(Integer) # JV_HMSTD field 18 — SOH signal
    lnd_val:  Mapped[int | None] = mapped_column(Integer) # LND_VAL field 41 — Land value
    exmpt_01: Mapped[int | None] = mapped_column(Integer) # EXMPT_01 field 110 — Homestead exemption

    # ------------------------------------------------------------------ #
    # NAL — Parcel change / condition / disaster flags                     #
    # ------------------------------------------------------------------ #
    nconst_val: Mapped[int | None] = mapped_column(Integer)      # NCONST_VAL field 36
    del_val:    Mapped[int | None] = mapped_column(Integer)      # DEL_VAL field 37
    par_splt:   Mapped[str | None] = mapped_column(String(5))    # PAR_SPLT field 38
    distr_cd:   Mapped[int | None] = mapped_column(Integer)      # DISTR_CD field 39
    distr_yr:   Mapped[int | None] = mapped_column(Integer)      # DISTR_YR field 40
    spass_cd:   Mapped[str | None] = mapped_column(String(1))    # SPASS_CD field 10

    # ------------------------------------------------------------------ #
    # NAL — Land and improvement fields                                    #
    # ------------------------------------------------------------------ #
    lnd_sqfoot:   Mapped[int | None] = mapped_column(Integer)  # LND_SQFOOT field 44
    dt_last_inspt: Mapped[str | None] = mapped_column(String(4)) # DT_LAST_INSPT field 45 — MMYY
    imp_qual:     Mapped[int | None] = mapped_column(Integer)  # IMP_QUAL field 46
    const_class:  Mapped[int | None] = mapped_column(Integer)  # CONST_CLASS field 47 — blank for SFR
    eff_yr_blt:   Mapped[int | None] = mapped_column(Integer)  # EFF_YR_BLT field 48
    act_yr_blt:   Mapped[int | None] = mapped_column(Integer)  # ACT_YR_BLT field 49
    tot_lvg_area: Mapped[int | None] = mapped_column(Integer)  # TOT_LVG_AREA field 50
    no_buldng:    Mapped[int | None] = mapped_column(Integer)  # NO_BULDNG field 51
    no_res_unts:  Mapped[int | None] = mapped_column(Integer)  # NO_RES_UNTS field 52
    spec_feat_val: Mapped[int | None] = mapped_column(Integer) # SPEC_FEAT_VAL field 53

    # ------------------------------------------------------------------ #
    # NAL — Embedded sale history (fields 54-73, merged from SDF by DOR)  #
    # Up to two most recent qualifying sales per parcel.                  #
    # For complete sale history use sales_comps table (SDF source).       #
    # ------------------------------------------------------------------ #
    multi_par_sal1: Mapped[str | None] = mapped_column(String(1))  # field 54
    qual_cd1:       Mapped[str | None] = mapped_column(String(2))  # field 55
    vi_cd1:         Mapped[str | None] = mapped_column(String(1))  # field 56
    sale_prc1:      Mapped[int | None] = mapped_column(Integer)    # field 57
    sale_yr1:       Mapped[int | None] = mapped_column(Integer)    # field 58
    sale_mo1:       Mapped[int | None] = mapped_column(Integer)    # field 59
    sal_chng_cd1:   Mapped[str | None] = mapped_column(String(1))  # field 63

    multi_par_sal2: Mapped[str | None] = mapped_column(String(1))  # field 64
    qual_cd2:       Mapped[str | None] = mapped_column(String(2))  # field 65
    vi_cd2:         Mapped[str | None] = mapped_column(String(1))  # field 66
    sale_prc2:      Mapped[int | None] = mapped_column(Integer)    # field 67
    sale_yr2:       Mapped[int | None] = mapped_column(Integer)    # field 68
    sale_mo2:       Mapped[int | None] = mapped_column(Integer)    # field 69
    sal_chng_cd2:   Mapped[str | None] = mapped_column(String(1))  # field 73

    # ------------------------------------------------------------------ #
    # NAL — Owner and mailing address (fields 74-80)                      #
    # ------------------------------------------------------------------ #
    own_name:      Mapped[str | None] = mapped_column(String(50))   # OWN_NAME field 74
    own_addr1:     Mapped[str | None] = mapped_column(String(40))   # OWN_ADDR1 field 75
    own_addr2:     Mapped[str | None] = mapped_column(String(40))   # OWN_ADDR2 field 76
    own_city:      Mapped[str | None] = mapped_column(String(40))   # OWN_CITY field 77
    own_state:     Mapped[str | None] = mapped_column(String(25))   # OWN_STATE field 78
    own_zipcd:     Mapped[str | None] = mapped_column(String(5))    # OWN_ZIPCD field 79
    own_state_dom: Mapped[str | None] = mapped_column(String(2))    # OWN_STATE_DOM field 80

    # ------------------------------------------------------------------ #
    # NAL — Physical / situs address (fields 99-102)                      #
    # ------------------------------------------------------------------ #
    phy_addr1: Mapped[str | None] = mapped_column(String(40))  # PHY_ADDR1 field 99
    phy_city:  Mapped[str | None] = mapped_column(String(40))  # PHY_CITY field 101
    phy_zipcd: Mapped[str | None] = mapped_column(String(5))   # PHY_ZIPCD field 102

    # ------------------------------------------------------------------ #
    # NAL — Geographic / location fields                                   #
    # ------------------------------------------------------------------ #
    mkt_ar:   Mapped[str | None] = mapped_column(String(3))   # MKT_AR field 91
    nbrhd_cd: Mapped[str | None] = mapped_column(String(10))  # NBRHD_CD field 92
    twn:      Mapped[str | None] = mapped_column(String(3))   # TWN field 95
    rng:      Mapped[str | None] = mapped_column(String(3))   # RNG field 96
    sec:      Mapped[str | None] = mapped_column(String(3))   # SEC field 97
    census_bk: Mapped[str | None] = mapped_column(String(16)) # CENSUS_BK field 98
    alt_key:  Mapped[str | None] = mapped_column(String(26))  # ALT_KEY field 103
    s_legal:  Mapped[str | None] = mapped_column(String(30))  # S_LEGAL field 88

    # ------------------------------------------------------------------ #
    # Derived — computed during Stage 1 ingest, not raw NAL fields        #
    # ------------------------------------------------------------------ #
    absentee_owner: Mapped[bool | None] = mapped_column(Boolean)
    # own_addr1/own_zipcd != phy_addr1/phy_zipcd

    improvement_to_land_ratio: Mapped[float | None] = mapped_column(Numeric(8, 4))
    # (jv - lnd_val) / lnd_val

    soh_compression_ratio: Mapped[float | None] = mapped_column(Numeric(6, 4))
    # av_nsd / jv — approaches 1.0 when SOH cap is not constraining

    years_since_last_sale: Mapped[int | None] = mapped_column(Integer)
    # asmnt_yr - sale_yr1

    # ------------------------------------------------------------------ #
    # CAMA — Stage 2 enrichment (nullable until CAMA pipeline runs)       #
    # ------------------------------------------------------------------ #
    foundation_type:    Mapped[str | None] = mapped_column(String(100))
    exterior_wall:      Mapped[str | None] = mapped_column(String(100))
    roof_type:          Mapped[str | None] = mapped_column(String(100))
    bedrooms:           Mapped[int | None] = mapped_column(Integer)
    bathrooms:          Mapped[float | None] = mapped_column(Numeric(4, 1))
    bed_bath_source:    Mapped[str | None] = mapped_column(String(50))
    cama_quality_code:  Mapped[str | None] = mapped_column(String(10))
    cama_condition_code: Mapped[str | None] = mapped_column(String(10))
    cama_enriched_at:   Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # ------------------------------------------------------------------ #
    # Geometry (PostGIS) — centroid POINT from GIS shapefile              #
    # ------------------------------------------------------------------ #
    geom:      Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=True
    )
    latitude:  Mapped[float | None] = mapped_column(Numeric(10, 7))
    longitude: Mapped[float | None] = mapped_column(Numeric(10, 7))

    # ------------------------------------------------------------------ #
    # MQI filter result                                                    #
    # ------------------------------------------------------------------ #
    mqi_qualified:        Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mqi_qualified_at:     Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mqi_rejection_reasons: Mapped[list | None] = mapped_column(JSONB)
    mqi_stage:            Mapped[str | None] = mapped_column(String(10))
    # Stage at which parcel was last evaluated: 'NAL', 'CAMA', 'FULL'

    # ------------------------------------------------------------------ #
    # Phase 2 scoring slots — NULL until Phase 2 pipeline is built        #
    # ------------------------------------------------------------------ #
    seller_probability_score: Mapped[float | None] = mapped_column(Numeric(5, 4))
    seller_score_updated_at:  Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    permit_count:             Mapped[int | None] = mapped_column(Integer)
    estimated_rehab_per_sqft: Mapped[float | None] = mapped_column(Numeric(6, 2))
    # Falls back to filter_profile.rehab_cost_per_sqft when NULL

    # ------------------------------------------------------------------ #
    # Raw data capture                                                     #
    # ------------------------------------------------------------------ #
    raw_nal_json:  Mapped[dict | None] = mapped_column(JSONB)
    raw_cama_json: Mapped[dict | None] = mapped_column(JSONB)

    # ------------------------------------------------------------------ #
    # Audit timestamps                                                     #
    # ------------------------------------------------------------------ #
    nal_ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False
    )

    # ------------------------------------------------------------------ #
    # Relationships                                                        #
    # ------------------------------------------------------------------ #
    value_history: Mapped[list[PropertyValueHistory]] = relationship(
        "PropertyValueHistory",
        back_populates="property",
        cascade="all, delete-orphan",
        primaryjoin="and_(Property.county_fips==PropertyValueHistory.county_fips, "
                    "Property.parcel_id==PropertyValueHistory.parcel_id)",
        foreign_keys="[PropertyValueHistory.county_fips, PropertyValueHistory.parcel_id]",
    )
    listing_events: Mapped[list[ListingEvent]] = relationship(
        "ListingEvent",
        back_populates="property",
        cascade="all, delete-orphan",
        primaryjoin="and_(Property.county_fips==ListingEvent.county_fips, "
                    "Property.parcel_id==ListingEvent.parcel_id)",
        foreign_keys="[ListingEvent.county_fips, ListingEvent.parcel_id]",
    )
