"""
ZestimateCache — append-only; one row per parcel per fetch.
Staleness is checked against filter_profile.zestimate_staleness_days.
"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Numeric, Index, func
from sqlalchemy.orm import Mapped, mapped_column
from real_invest_fl.db.base import Base


class ZestimateCache(Base):
    __tablename__ = "zestimate_cache"
    __table_args__ = (
        Index("ix_zc_county_parcel_fetched", "county_fips", "parcel_id", "fetched_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    county_fips: Mapped[str] = mapped_column(String(5), nullable=False)
    parcel_id: Mapped[str] = mapped_column(String(30), nullable=False)
    zestimate_value: Mapped[int | None] = mapped_column(Integer)
    zestimate_last_updated: Mapped[str | None] = mapped_column(String(30))
    fetch_url: Mapped[str | None] = mapped_column(String(1000))
    http_status: Mapped[int | None] = mapped_column(Integer)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
