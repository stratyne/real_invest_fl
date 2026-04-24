"""
Property — Master Qualified Inventory (MQI).
Primary key is (county_fips, parcel_id) — composite, county-scoped.
NAL fields mapped directly; CAMA fields populated in Stage 2.
Phase 2 fields (seller_probability_score, permit_count) are nullable
and will remain NULL until their respective pipeline stages are built.
"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import (
    String, Integer, Boolean, DateTime, Text,
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
        Index("ix_properties_county_fips", "county_fips"),
        Index("ix_properties_zip_code", "zip_code"),
        Index("ix_properties_dor_use_code", "dor_use_code"),
        Index("ix_properties_const_class", "construction_class"),
        Index("ix_properties_act_yr_blt", "actual_year_built"),
        Index("ix_properties_mqi_qualified", "mqi_qualified"),
    )

    # --- Primary key ---
    county_fips: Mapped[str] = mapped_column(String(5), primary_key=True)
    parcel_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    parcel_id_normalized: Mapped[str] = mapped_column(String(30), nullable=False, index=True)

    # --- NAL Stage 1 fields ---
    dor_county_no: Mapped[int | None] = mapped_column(Integer)
    assessment_year: Mapped[int | None] = mapped_column(Integer)
    dor_use_code: Mapped[str | None] = mapped_column(String(10))
    pa_use_code: Mapped[str | None] = mapped_column(String(10))

    # Assessed values (from NAL)
    just_value: Mapped[int | None] = mapped_column(Integer)
    assessed_value: Mapped[int | None] = mapped_column(Integer)
    taxable_value: Mapped[int | None] = mapped_column(Integer)

    # Construction (from NAL field 47)
    construction_class: Mapped[int | None] = mapped_column(Integer)
    # NAL construction class codes:
    # 1=Wood frame, 2=Concrete/Steel (commercial), 3=Masonry (cinder/concrete block),
    # 4=Steel, 5=Prefab/Mobile, 6=Other — only class 3 passes NAL filter.

    # Year built (from NAL fields 48-49)
    effective_year_built: Mapped[int | None] = mapped_column(Integer)
    actual_year_built: Mapped[int | None] = mapped_column(Integer)

    # Size (from NAL field 50)
    total_living_area: Mapped[int | None] = mapped_column(Integer)
    land_square_footage: Mapped[int | None] = mapped_column(Integer)

    # Building counts
    num_buildings: Mapped[int | None] = mapped_column(Integer)
    num_residential_units: Mapped[int | None] = mapped_column(Integer)

    # Owner / mailing address (from NAL fields 74-94)
    owner_name: Mapped[str | None] = mapped_column(String(200))
    owner_address_line1: Mapped[str | None] = mapped_column(String(200))
    owner_address_line2: Mapped[str | None] = mapped_column(String(200))
    owner_city: Mapped[str | None] = mapped_column(String(100))
    owner_state: Mapped[str | None] = mapped_column(String(2))
    owner_zip: Mapped[str | None] = mapped_column(String(10))

    # Property / situs address
    situs_address: Mapped[str | None] = mapped_column(String(300))
    situs_city: Mapped[str | None] = mapped_column(String(100))
    situs_state: Mapped[str | None] = mapped_column(String(2))
    zip_code: Mapped[str | None] = mapped_column(String(10))

    # Absentee owner flag — derived: owner mailing ZIP != situs ZIP
    absentee_owner: Mapped[bool | None] = mapped_column(Boolean)

    # --- CAMA Stage 2 fields (nullable until CAMA enrichment runs) ---
    foundation_type: Mapped[str | None] = mapped_column(String(100))
    exterior_wall: Mapped[str | None] = mapped_column(String(100))
    roof_type: Mapped[str | None] = mapped_column(String(100))
    bedrooms: Mapped[int | None] = mapped_column(Integer)
    bathrooms: Mapped[float | None] = mapped_column(Numeric(4, 1))
    cama_quality_code: Mapped[str | None] = mapped_column(String(10))
    cama_condition_code: Mapped[str | None] = mapped_column(String(10))
    cama_enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # --- Geometry (PostGIS) ---
    geom: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=True
    )
    latitude: Mapped[float | None] = mapped_column(Numeric(10, 7))
    longitude: Mapped[float | None] = mapped_column(Numeric(10, 7))

    # --- MQI filter result ---
    mqi_qualified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mqi_qualified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mqi_rejection_reasons: Mapped[list | None] = mapped_column(JSONB)
    # Stage at which this parcel was last evaluated: 'NAL', 'CAMA', 'FULL'
    mqi_stage: Mapped[str | None] = mapped_column(String(10))

    # --- Phase 2 scoring slots (nullable, populated in Phase 2) ---
    seller_probability_score: Mapped[float | None] = mapped_column(Numeric(5, 4))
    seller_score_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    permit_count: Mapped[int | None] = mapped_column(Integer)
    estimated_rehab_per_sqft: Mapped[float | None] = mapped_column(Numeric(6, 2))
    # Falls back to filter_profile.rehab_cost_per_sqft when NULL

    # --- Raw data ---
    raw_nal_json: Mapped[dict | None] = mapped_column(JSONB)
    raw_cama_json: Mapped[dict | None] = mapped_column(JSONB)

    # --- Audit ---
    nal_ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False
    )

    # --- Relationships ---
    value_history: Mapped[list[PropertyValueHistory]] = relationship(
        "PropertyValueHistory", back_populates="property",
        cascade="all, delete-orphan",
        primaryjoin="and_(Property.county_fips==foreign(PropertyValueHistory.county_fips), "
                    "Property.parcel_id==foreign(PropertyValueHistory.parcel_id))"
    )
    listing_events: Mapped[list[ListingEvent]] = relationship(
        "ListingEvent", back_populates="property",
        cascade="all, delete-orphan",
        primaryjoin="and_(Property.county_fips==foreign(ListingEvent.county_fips), "
                    "Property.parcel_id==foreign(ListingEvent.parcel_id))"
    )
