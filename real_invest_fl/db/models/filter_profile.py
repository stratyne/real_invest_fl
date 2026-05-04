"""
FilterProfile — versioned, named investment filter sets.

filter_criteria stores the complete filter vocabulary document as JSONB.
This is the single source of truth for all filter dimensions.
Engine/operational configuration (comp settings, scoring weights,
outreach settings, rehab cost) are retained as scalar columns because
they govern pipeline behaviour, not property selection criteria.

Uniqueness model:
  System profiles (user_id IS NULL): unique on (county_fips, profile_name).
  User profiles   (user_id NOT NULL): unique on (user_id, county_fips, profile_name).
  Enforced via two partial unique indexes — see __table_args__.
  The old global unique constraint on profile_name alone was dropped in v0.13.
"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import String, Integer, Float, Boolean, DateTime, Text, Index, ForeignKey, func
from sqlalchemy import text as sa_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from real_invest_fl.db.base import Base


class FilterProfile(Base):
    __tablename__ = "filter_profiles"
    __table_args__ = (
        Index(
            "uq_fp_system_county_name",
            "county_fips",
            "profile_name",
            unique=True,
            postgresql_where=sa_text("user_id IS NULL"),
        ),
        Index(
            "uq_fp_user_county_name",
            "user_id",
            "county_fips",
            "profile_name",
            unique=True,
            postgresql_where=sa_text("user_id IS NOT NULL"),
        ),
    )

    # ------------------------------------------------------------------ #
    # Identity                                                             #
    # ------------------------------------------------------------------ #
    id:           Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # profile_name: no unique=True here — uniqueness handled by partial indexes above
    profile_name: Mapped[str] = mapped_column(String(100), nullable=False)
    county_fips:  Mapped[str] = mapped_column(String(5), nullable=False)
    description:  Mapped[str | None] = mapped_column(Text)
    is_active:    Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version:      Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # ------------------------------------------------------------------ #
    # Ownership — NULL = system catalog profile                            #
    # ------------------------------------------------------------------ #

    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ------------------------------------------------------------------ #
    # Filter vocabulary — single source of truth                          #
    # ------------------------------------------------------------------ #
    filter_criteria: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # ------------------------------------------------------------------ #
    # Comp engine configuration                                            #
    # ------------------------------------------------------------------ #
    rehab_cost_per_sqft:       Mapped[float] = mapped_column(Float, nullable=False, default=22.00)
    min_comp_sales_for_arv:    Mapped[int]   = mapped_column(Integer, nullable=False, default=3)
    comp_radius_miles:         Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    comp_year_built_tolerance: Mapped[int]   = mapped_column(Integer, nullable=False, default=15)

    # ------------------------------------------------------------------ #
    # Scoring weights                                                      #
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

    # ------------------------------------------------------------------ #
    # Relationships                                                        #
    # ------------------------------------------------------------------ #
    owner: Mapped[User | None] = relationship(
        "User",
        back_populates="filter_profiles",
        foreign_keys="[FilterProfile.user_id]",
    )

    scores: Mapped[list[ListingScore]] = relationship(
        "ListingScore",
        back_populates="filter_profile",
        foreign_keys="[ListingScore.filter_profile_id]",
        cascade="all, delete-orphan",
    )
