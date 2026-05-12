"""
SkipTraceCache — cached skip-trace lookup results per parcel.

One cached result per (county_fips, parcel_id) — uq_stc_county_parcel.
TTL controlled by settings.SKIP_TRACE_CACHE_TTL_DAYS. expires_at is set
at write time as fetched_at + TTL. ix_stc_expires_at supports cleanup sweeps.

provider records the data source. Default: 'BATCHDATA'. No CHECK constraint —
additional providers may be added without migration.

Live BatchData API integration is deferred (item 44). The skip_trace route
returns a cached row if present and not expired, and 501 when
BATCHDATA_API_KEY is not configured.
"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import (
    String, Integer, DateTime, Index,
    UniqueConstraint, func
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from real_invest_fl.db.base import Base


class SkipTraceCache(Base):
    __tablename__ = "skip_trace_cache"
    __table_args__ = (
        UniqueConstraint(
            "county_fips", "parcel_id",
            name="uq_stc_county_parcel",
        ),
        Index("ix_stc_expires_at", "expires_at"),
    )

    # ------------------------------------------------------------------ #
    # Primary key                                                          #
    # ------------------------------------------------------------------ #
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ------------------------------------------------------------------ #
    # Scope                                                                #
    # ------------------------------------------------------------------ #
    county_fips: Mapped[str] = mapped_column(String(5),  nullable=False)
    parcel_id:   Mapped[str] = mapped_column(String(30), nullable=False)

    # ------------------------------------------------------------------ #
    # Result snapshot                                                      #
    # ------------------------------------------------------------------ #
    skip_trace_result: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # ------------------------------------------------------------------ #
    # TTL / provenance                                                     #
    # ------------------------------------------------------------------ #
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # No CHECK constraint on provider — additional providers require no migration
    provider: Mapped[str] = mapped_column(
        String(50), nullable=False, default="BATCHDATA"
    )

    # ------------------------------------------------------------------ #
    # Audit                                                                #
    # ------------------------------------------------------------------ #
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ------------------------------------------------------------------ #
    # Relationships                                                        #
    # Note: SkipTraceCache has no FK to users or properties — it is a     #
    # keyed cache table. Navigation is by (county_fips, parcel_id) lookup #
    # at the service layer, not via ORM relationship.                      #
    # ------------------------------------------------------------------ #
