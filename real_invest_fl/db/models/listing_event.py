"""
ListingEvent — append-only record of each scrape event. Immutable
facts about what was scraped, from what source, and when.

Scoring output (deal_score, passed_filters, filter_rejection_reasons)
lives in listing_scores — one row per (event, filter_profile).
See listing_score.py.

signal_tier and signal_type support the Phase 2 hybrid signal-aggregator
+ traditional listing model.

signal_tier:
    1 = Government distress records (foreclosure sales, tax deeds,
        lis pendens, tax delinquency) — highest motivation signal
    2 = Bulk public data / government auction portals (HUD, surplus,
        tax deed auctions) — high signal, minimal scraping risk
    3 = Commercial listing platforms / FSBO (Zillow, Redfin, Craigslist,
        Auction.com) — listing confirmation layer

signal_type examples:
    foreclosure_sale | tax_deed | lis_pendens | tax_delinquent |
    fsbo | active_listing | expired_listing | auction | surplus | hud
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
        Index("ix_le_county_parcel",  "county_fips", "parcel_id"),
        Index("ix_le_status",         "workflow_status"),
        Index("ix_le_listing_type",   "listing_type"),
        Index("ix_le_signal_tier",    "signal_tier"),
        Index("ix_le_signal_type",    "signal_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    county_fips: Mapped[str] = mapped_column(String(5),  nullable=False)
    parcel_id:   Mapped[str] = mapped_column(String(30), nullable=False)

    # ------------------------------------------------------------------ #
    # Signal classification — Phase 2 hybrid model                        #
    # ------------------------------------------------------------------ #
    signal_tier: Mapped[int | None] = mapped_column(Integer)
    # 1 = Gov distress | 2 = Gov auction/bulk | 3 = Commercial/FSBO

    signal_type: Mapped[str | None] = mapped_column(String(50))
    # foreclosure_sale | tax_deed | lis_pendens | tax_delinquent |
    # fsbo | active_listing | expired_listing | auction | surplus | hud

    # ------------------------------------------------------------------ #
    # Listing data                                                         #
    # ------------------------------------------------------------------ #
    listing_type: Mapped[str | None] = mapped_column(String(50))
    # MLS status when available: Active | Pending | Expired | Cancelled
    # Separate from signal_type — reserved for MLS-sourced classification

    list_price:         Mapped[int | None]      = mapped_column(Integer)
    list_date:          Mapped[date | None]      = mapped_column(Date)
    expiry_date:        Mapped[date | None]      = mapped_column(Date)
    days_on_market:     Mapped[int | None]       = mapped_column(Integer)
    source:             Mapped[str | None]       = mapped_column(String(100))
    listing_url:        Mapped[str | None]       = mapped_column(String(1000))
    listing_agent_name: Mapped[str | None]       = mapped_column(String(200))
    listing_agent_email: Mapped[str | None]      = mapped_column(String(200))
    listing_agent_phone: Mapped[str | None]      = mapped_column(String(30))
    mls_number:         Mapped[str | None]       = mapped_column(String(50))

    # ------------------------------------------------------------------ #
    # Derived financial fields                                             #
    # ------------------------------------------------------------------ #
    price_per_sqft:     Mapped[float | None]     = mapped_column(Numeric(8, 2))
    arv_estimate:       Mapped[int | None]       = mapped_column(Integer)
    arv_source:         Mapped[str | None]       = mapped_column(String(20))
    # 'JV' | 'SDF_COMPS' | 'ZESTIMATE' | 'MANUAL'
    rehab_cost_estimate: Mapped[int | None]      = mapped_column(Integer)
    arv_spread:         Mapped[int | None]       = mapped_column(Integer)
    # arv_estimate - list_price - rehab_cost_estimate

    # ------------------------------------------------------------------ #
    # Zestimate (secondary signal)                                         #
    # ------------------------------------------------------------------ #
    zestimate_value:        Mapped[int | None]   = mapped_column(Integer)
    zestimate_discount_pct: Mapped[float | None] = mapped_column(Numeric(6, 3))
    zestimate_fetched_at:   Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # ------------------------------------------------------------------ #
    # Workflow status                                                      #
    # ------------------------------------------------------------------ #
    workflow_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="NEW"
    )
    # NEW | REVIEWED | APPROVE_SEND | SENT | RESPONDED | REJECTED | CLOSED

    notes:            Mapped[str | None]  = mapped_column(Text)
    raw_listing_json: Mapped[dict | None] = mapped_column(JSONB)

    # ------------------------------------------------------------------ #
    # Audit                                                                #
    # ------------------------------------------------------------------ #
    scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
    property: Mapped[Property] = relationship(
        "Property",
        back_populates="listing_events",
        primaryjoin="and_(ListingEvent.county_fips==Property.county_fips, "
                    "ListingEvent.parcel_id==Property.parcel_id)",
        foreign_keys="[ListingEvent.county_fips, ListingEvent.parcel_id]",
    )

    scores: Mapped[list[ListingScore]] = relationship(
        "ListingScore",
        back_populates="listing_event",
        cascade="all, delete-orphan"
    )
