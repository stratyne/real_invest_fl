"""
IngestRun — audit record for every pipeline execution.

One row per run. Opened when a pipeline stage starts, closed
when it finishes or fails. Never updated after closed.
"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from real_invest_fl.db.base import Base


class IngestRun(Base):
    __tablename__ = "ingest_runs"

    # ------------------------------------------------------------------ #
    # Identity                                                             #
    # ------------------------------------------------------------------ #
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    run_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )
    # Valid values: 'NAL' | 'CAMA' | 'GIS' | 'LISTING' | 'ZESTIMATE'

    county_fips: Mapped[str] = mapped_column(
        String(5), nullable=False
    )
    source_file: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    run_status: Mapped[str] = mapped_column(
        String(20), nullable=False
    )
    # Valid values: 'RUNNING' | 'SUCCESS' | 'FAILED' | 'PARTIAL'

    # ------------------------------------------------------------------ #
    # Timing                                                               #
    # ------------------------------------------------------------------ #
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_seconds: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    # ------------------------------------------------------------------ #
    # Volume counters                                                      #
    # ------------------------------------------------------------------ #
    records_read: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    records_inserted: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    records_updated: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    records_rejected: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    records_skipped: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    # ------------------------------------------------------------------ #
    # Quality                                                              #
    # ------------------------------------------------------------------ #
    filter_profile_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    rejection_summary: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )
    # Structure: {"reason_code": count, ...}
    # e.g. {"dor_uc_mismatch": 42150, "year_built_too_old": 312}

    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    error_traceback: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    # ------------------------------------------------------------------ #
    # Audit                                                                #
    # ------------------------------------------------------------------ #
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    