"""
FilterProfile — versioned, named investment filter sets.
All parameters that were previously hard-coded in constants.py or filters.py
now live here as JSON fields, queryable and editable via the UI.
"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from real_invest_fl.db.base import Base


class FilterProfile(Base):
    __tablename__ = "filter_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    county_fips: Mapped[str] = mapped_column(String(5), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Financial filters
    max_list_price: Mapped[int] = mapped_column(Integer, nullable=False, default=225000)
    min_list_price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    target_beds: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    target_baths: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    min_year_built: Mapped[int] = mapped_column(Integer, nullable=False, default=1950)
    primary_max_year_built: Mapped[int] = mapped_column(Integer, nullable=False, default=1960)
    rehab_cost_per_sqft: Mapped[float] = mapped_column(nullable=False, default=22.00)
    min_arv_spread: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    min_zestimate_discount_pct: Mapped[float] = mapped_column(nullable=False, default=0.0)
    zestimate_staleness_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)

    # Comp engine settings
    min_comp_sales_for_arv: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    comp_radius_miles: Mapped[float] = mapped_column(nullable=False, default=1.0)
    comp_year_built_tolerance: Mapped[int] = mapped_column(Integer, nullable=False, default=15)

    # Keyword and code lists stored as JSONB arrays
    allowed_dor_use_codes: Mapped[list] = mapped_column(JSONB, nullable=False, default=["001"])
    allowed_construction_classes: Mapped[list] = mapped_column(JSONB, nullable=False, default=[3])
    allowed_foundation_keywords: Mapped[list] = mapped_column(JSONB, nullable=False, default=[])
    disallowed_foundation_keywords: Mapped[list] = mapped_column(JSONB, nullable=False, default=[])
    allowed_construction_keywords: Mapped[list] = mapped_column(JSONB, nullable=False, default=[])
    disallowed_property_types: Mapped[list] = mapped_column(JSONB, nullable=False, default=[])

    # Priority and scoring weights
    listing_type_priority: Mapped[dict] = mapped_column(JSONB, nullable=False, default={})
    deal_score_weights: Mapped[dict] = mapped_column(JSONB, nullable=False, default={})

    # Outreach settings
    allow_automated_outreach: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    max_outreach_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False
    )
