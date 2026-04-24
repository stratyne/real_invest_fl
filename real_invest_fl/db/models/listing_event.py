"""
ListingEvent — append-only record each time a qualified MQI property
appears in a listing feed. deal_score and deal_score_version are the
output of the multi-signal scoring engine (Phase 1 partial, Phase 2 full).
"""
from __future__ import annotations
from datetime import datetime, date
from sqlalchemy import (
    String, Integer, Boolean, DateTime, Date,
    Text, Numeric, Index, func
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from real_invest_fl.db.base import Base


class ListingEvent(Base):
    __tablename__ = "listing_events"
    __table_args__ = (
        Index("ix_le_county_parcel", "county_fips", "parcel_id"),
        Index("ix_le_status", "workflow_status"),
        Index("ix_le_listing_type", "listing_type"),
        Index("ix_le_deal_score", "deal_score"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    county_fips: Mapped[str] = mapped_column(String(5), nullable=False)
    parcel_id: Mapped[str] = mapped_column(String(30), nullable=False)

    # Listing data
    listing_type: Mapped[str | None] = mapped_column(String(50))
    # FSBO | Foreclosure | Expired | MLS/Portal | Auction
    list_price: Mapped[int | None] = mapped_column(Integer)
    list_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    days_on_market: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str | None] = mapped_column(String(100))
    listing_url: Mapped[str | None] = mapped_column(String(1000))
    listing_agent_name: Mapped[str | None] = mapped_column(String(200))
    listing_agent_email: Mapped[str | None] = mapped_column(String(200))
    listing_agent_phone: Mapped[str | None] = mapped_column(String(30))
    mls_number: Mapped[str | None] = mapped_column(String(50))

    # Derived financial fields
    price_per_sqft: Mapped[float | None] = mapped_column(Numeric(8, 2))
    arv_estimate: Mapped[int | None] = mapped_column(Integer)
    arv_source: Mapped[str | None] = mapped_column(String(20))
    # 'SDF_COMPS' | 'ZESTIMATE' | 'MANUAL'
    rehab_cost_estimate: Mapped[int | None] = mapped_column(Integer)
    arv_spread: Mapped[int | None] = mapped_column(Integer)
    # arv_estimate - list_price - rehab_cost_estimate

    # Zestimate (secondary signal)
    zestimate_value: Mapped[int | None] = mapped_column(Integer)
    zestimate_discount_pct: Mapped[float | None] = mapped_column(Numeric(6, 3))
    zestimate_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Multi-signal deal score
    deal_score: Mapped[float | None] = mapped_column(Numeric(5, 4))
    deal_score_version: Mapped[str | None] = mapped_column(String(20))
    deal_score_components: Mapped[dict | None] = mapped_column(JSONB)
    # Stores individual component scores for UI drill-down

    # Filter evaluation result
    filter_profile_id: Mapped[int | None] = mapped_column(Integer)
    passed_filters: Mapped[bool | None] = mapped_column(Boolean)
    filter_rejection_reasons: Mapped[list | None] = mapped_column(JSONB)

    # Workflow status
    workflow_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="NEW"
    )
    # NEW | REVIEWED | APPROVE_SEND | SENT | RESPONDED | REJECTED | CLOSED

    notes: Mapped[str | None] = mapped_column(Text)
    raw_listing_json: Mapped[dict | None] = mapped_column(JSONB)

    # Audit
    scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False
    )

    property: Mapped[Property] = relationship(
        "Property", back_populates="listing_events",
        primaryjoin="and_(ListingEvent.county_fips==foreign(Property.county_fips), "
                    "ListingEvent.parcel_id==foreign(Property.parcel_id))"
    )
