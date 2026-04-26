"""
FilterProfile — versioned, named investment filter sets.

filter_criteria stores the complete filter vocabulary document as JSONB.
This is the single source of truth for all filter dimensions.
Engine/operational configuration (comp settings, scoring weights,
outreach settings, rehab cost) are retained as scalar columns because
they govern pipeline behaviour, not property selection criteria.
"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import String, Integer, Float, Boolean, DateTime, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from real_invest_fl.db.base import Base


class FilterProfile(Base):
    __tablename__ = "filter_profiles"

    # ------------------------------------------------------------------ #
    # Identity                                                             #
    # ------------------------------------------------------------------ #
    id:           Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    county_fips:  Mapped[str] = mapped_column(String(5), nullable=False)
    description:  Mapped[str | None] = mapped_column(Text)
    is_active:    Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version:      Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # ------------------------------------------------------------------ #
    # Filter vocabulary — single source of truth                          #
    # Stores the complete filter_criteria document from                   #
    # config/filter_profiles/<profile>.json                               #
    # ------------------------------------------------------------------ #
    filter_criteria: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # ------------------------------------------------------------------ #
    # Comp engine configuration                                            #
    # These govern ARV calculation behaviour, not property selection.     #
    # ------------------------------------------------------------------ #
    rehab_cost_per_sqft:      Mapped[float] = mapped_column(Float, nullable=False, default=22.00)
    min_comp_sales_for_arv:   Mapped[int]   = mapped_column(Integer, nullable=False, default=3)
    comp_radius_miles:        Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    comp_year_built_tolerance: Mapped[int]  = mapped_column(Integer, nullable=False, default=15)

    # ------------------------------------------------------------------ #
    # Scoring weights                                                      #
    # Keyed by signal name, values are floats summing to 1.0              #
    # ------------------------------------------------------------------ #
    listing_type_priority: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    deal_score_weights:    Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # ------------------------------------------------------------------ #
    # Outreach configuration                                               #
    # ------------------------------------------------------------------ #
    allow_automated_outreach: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    max_outreach_attempts:    Mapped[int]  = mapped_column(Integer, nullable=False, default=3)

    # ------------------------------------------------------------------ #
    # Audit                                                                #
    # ------------------------------------------------------------------ #
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False
    )
