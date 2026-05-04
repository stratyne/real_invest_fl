"""
ListingScore — per-user, per-profile scoring result for a listing event.

Separated from listing_events deliberately. listing_events is an
append-only event log — immutable facts about what was scraped and when.
ListingScore is the derived, recomputable output of running a user's
filter profile against those facts.

One row per (listing_event, filter_profile). The unique constraint
uq_ls_event_profile ensures upserts are safe and recompute never
produces duplicate rows.

Recompute scope: when a user saves or modifies a filter profile,
only listing_scores rows for (user_id, filter_profile_id) are
touched. The event log is never modified.
"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import (
    Integer, String, Boolean, Numeric, DateTime,
    ForeignKey, UniqueConstraint, Index, func
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from real_invest_fl.db.base import Base


class ListingScore(Base):
    __tablename__ = "listing_scores"
    __table_args__ = (
        UniqueConstraint(
            'listing_event_id', 'filter_profile_id',
            name='uq_ls_event_profile'
        ),
        Index('ix_ls_user_profile',      'user_id', 'filter_profile_id'),
        Index('ix_ls_user_county_score', 'user_id', 'county_fips', 'deal_score'),
        Index('ix_ls_passed_filters',    'filter_profile_id', 'passed_filters'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ------------------------------------------------------------------ #
    # Foreign keys                                                        #
    # ------------------------------------------------------------------ #
    listing_event_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('listing_events.id', ondelete='CASCADE', name='fk_ls_listing_event_id'),
        nullable=False
    )
    filter_profile_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('filter_profiles.id', ondelete='CASCADE', name='fk_ls_filter_profile_id'),
        nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('users.id', ondelete='CASCADE', name='fk_ls_user_id'),
        nullable=False
    )

    # Denormalized for query performance — avoids join to listing_events
    # on the most common retrieval pattern (all scores for a user/county)
    county_fips: Mapped[str] = mapped_column(String(5), nullable=False)

    # ------------------------------------------------------------------ #
    # Filter evaluation result                                            #
    # ------------------------------------------------------------------ #
    passed_filters:           Mapped[bool | None]  = mapped_column(Boolean)
    filter_rejection_reasons: Mapped[list | None]  = mapped_column(JSONB)

    # ------------------------------------------------------------------ #
    # Deal score                                                          #
    # ------------------------------------------------------------------ #
    deal_score:            Mapped[float | None] = mapped_column(Numeric(5, 4))
    deal_score_version:    Mapped[str | None]   = mapped_column(String(20))
    deal_score_components: Mapped[dict | None]  = mapped_column(JSONB)

    # ------------------------------------------------------------------ #
    # Audit                                                               #
    # ------------------------------------------------------------------ #
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    # ------------------------------------------------------------------ #
    # Relationships                                                       #
    # ------------------------------------------------------------------ #
    listing_event: Mapped[ListingEvent] = relationship(
        "ListingEvent",
        back_populates="scores"
    )
    filter_profile: Mapped[FilterProfile] = relationship(
        "FilterProfile",
        back_populates="scores"
    )
    user: Mapped[User] = relationship(
        "User",
        back_populates="listing_scores"
    )
