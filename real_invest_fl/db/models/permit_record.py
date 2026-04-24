"""
PermitRecord — Phase 2 slot.
Populated from Escambia County Building Services per-parcel queries.
Drives dynamic rehab cost estimation in the scoring engine.
"""
from __future__ import annotations
from datetime import datetime, date
from sqlalchemy import String, Integer, Boolean, DateTime, Date, Numeric, Text, Index, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from real_invest_fl.db.base import Base


class PermitRecord(Base):
    __tablename__ = "permit_records"
    __table_args__ = (
        Index("ix_pr_county_parcel", "county_fips", "parcel_id"),
        Index("ix_pr_permit_type", "permit_type"),
        Index("ix_pr_issue_date", "issue_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    county_fips: Mapped[str] = mapped_column(String(5), nullable=False)
    parcel_id: Mapped[str] = mapped_column(String(30), nullable=False)

    permit_number: Mapped[str | None] = mapped_column(String(100))
    permit_type: Mapped[str | None] = mapped_column(String(100))
    # ROOF | HVAC | ELECTRICAL | PLUMBING | ADDITION | RENOVATION | OTHER

    issue_date: Mapped[date | None] = mapped_column(Date)
    final_date: Mapped[date | None] = mapped_column(Date)
    permit_status: Mapped[str | None] = mapped_column(String(50))
    valuation: Mapped[float | None] = mapped_column(Numeric(12, 2))
    contractor_name: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    raw_json: Mapped[dict | None] = mapped_column(JSONB)

    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
