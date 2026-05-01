"""
SubscriptionBundle — named multi-county access packages.

Granting a bundle to a user means inserting one UserCountyAccess row
per bundle county for that user. That action is performed by a script
or Phase 4 admin UI — not automated here.
bundle_counties is the join table defining bundle membership.
"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Integer, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from real_invest_fl.db.base import Base


class SubscriptionBundle(Base):
    __tablename__ = "subscription_bundles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bundle_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    bundle_counties: Mapped[list[BundleCounty]] = relationship(
        "BundleCounty", back_populates="bundle", cascade="all, delete-orphan"
    )


class BundleCounty(Base):
    __tablename__ = "bundle_counties"

    bundle_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subscription_bundles.id", ondelete="CASCADE"),
        primary_key=True, nullable=False
    )
    county_fips: Mapped[str] = mapped_column(
        String(5), ForeignKey("counties.county_fips"),
        primary_key=True, nullable=False
    )

    # Relationships
    bundle: Mapped[SubscriptionBundle] = relationship(
        "SubscriptionBundle", back_populates="bundle_counties"
    )
