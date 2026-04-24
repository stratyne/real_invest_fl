"""
PublicRecordSignal — Phase 2 slot.
Stores pre-listing motivation signals from public records:
probate, lis pendens, tax delinquency, divorce, estate filings.
Schema slot is fully defined now; population deferred to Phase 2.
"""
from __future__ import annotations
from datetime import datetime, date
from sqlalchemy import String, Integer, Boolean, DateTime, Date, Text, Index, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from real_invest_fl.db.base import Base


class PublicRecordSignal(Base):
    __tablename__ = "public_records_signals"
    __table_args__ = (
        Index("ix_prs_county_parcel", "county_fips", "parcel_id"),
        Index("ix_prs_signal_type", "signal_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    county_fips: Mapped[str] = mapped_column(String(5), nullable=False)
    parcel_id: Mapped[str] = mapped_column(String(30), nullable=False)

    signal_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # PROBATE | LIS_PENDENS | TAX_DELINQUENT | DIVORCE | ESTATE | CODE_VIOLATION

    signal_date: Mapped[date | None] = mapped_column(Date)
    case_number: Mapped[str | None] = mapped_column(String(100))
    court_or_agency: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resolved_date: Mapped[date | None] = mapped_column(Date)
    source_url: Mapped[str | None] = mapped_column(String(1000))
    raw_json: Mapped[dict | None] = mapped_column(JSONB)

    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
