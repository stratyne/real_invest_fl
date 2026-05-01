"""
DataSourceStatus — live status board for all ingest sources.

One row per (source, county_fips) pair. Updated in-place on every
ingest run via upsert in source_status.update_source_status().
The UI reads this table to display source health and last-ingest
timestamps on the dashboard.

This is NOT an audit log. Use ingest_runs for historical per-run detail.

last_run_status valid values: 'SUCCESS' | 'FAILED' | 'PARTIAL'
last_run_at: timestamp of most recent run completion / status update.
last_success_at: timestamp of most recent run that completed SUCCESS.
                 NULL means this source has never had a successful run.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from real_invest_fl.db.base import Base


class DataSourceStatus(Base):
    __tablename__ = "data_source_status"

    # ------------------------------------------------------------------ #
    # Composite primary key                                                #
    # ------------------------------------------------------------------ #
    source: Mapped[str] = mapped_column(
        String(100), primary_key=True, nullable=False
    )
    # Matches listing_events.source exactly — e.g. 'escambia_clerk_taxsale'

    county_fips: Mapped[str] = mapped_column(
        String(5), primary_key=True, nullable=False
    )

    # ------------------------------------------------------------------ #
    # Identity                                                             #
    # ------------------------------------------------------------------ #
    display_name: Mapped[str] = mapped_column(
        String(200), nullable=False
    )
    # Human-readable label for UI — supplied by caller, e.g.
    # "Escambia Clerk – Tax Deed"

    # ------------------------------------------------------------------ #
    # Run status                                                           #
    # ------------------------------------------------------------------ #
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Timestamp of last run that completed SUCCESS.
    # Not updated on FAILED or PARTIAL runs.

    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Timestamp of the most recent run completion / status update,
    # regardless of outcome.

    last_run_status: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    # SUCCESS | FAILED | PARTIAL

    last_record_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    # Records inserted or updated in the most recent run.

    last_error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    # Short error message when last_run_status is FAILED.
    # Cleared to NULL on next SUCCESS run.

    # ------------------------------------------------------------------ #
    # Audit                                                                #
    # ------------------------------------------------------------------ #
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
