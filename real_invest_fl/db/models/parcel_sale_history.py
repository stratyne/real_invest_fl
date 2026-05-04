"""
ParcelSaleHistory — full ownership chain per parcel.

One row per recorded sale transaction, sourced from county property
appraiser websites (e.g. parcelview.srcpa.gov for Santa Rosa).
Captures every transaction regardless of qualification code —
arm's-length sales, nominal transfers, foreclosure deeds, quit claims.

This is distinct from sales_comps, which holds SDF-sourced qualified
arm's-length sales for the comp/ARV engine only.

ParcelSaleHistory powers:
    - Ownership duration (how long current owner has held the property)
    - Equity estimation (what they paid vs. current just value)
    - Distressed seller identification (nominal price, quit claim, etc.)
    - Investor pattern detection (serial flippers, institutional buyers)
    - Motivated seller scoring

Dedup key: (county_fips, parcel_id, sale_date, grantor, grantee)
    OR_BOOK / OR_PAGE are intentionally excluded — they are clerk
    recording references with no platform value.

Source coverage:
    Santa Rosa  — parcelview.srcpa.gov (confirmed working 2026-05-04)
    Escambia    — escpa.org (pending, site currently down)
    All others  — Phase 3, per-county PA website
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Index, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from real_invest_fl.db.base import Base


class ParcelSaleHistory(Base):
    __tablename__ = "parcel_sale_history"
    __table_args__ = (
        UniqueConstraint(
            "county_fips", "parcel_id", "sale_date", "grantor", "grantee",
            name="uq_psh_county_parcel_sale",
        ),
        Index("ix_psh_county_parcel", "county_fips", "parcel_id"),
        Index("ix_psh_sale_date", "sale_date"),
        Index("ix_psh_qualification_code", "qualification_code"),
        Index("ix_psh_grantor", "grantor"),
        Index("ix_psh_grantee", "grantee"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ------------------------------------------------------------------ #
    # Property identity                                                    #
    # ------------------------------------------------------------------ #
    county_fips: Mapped[str] = mapped_column(String(5), nullable=False)
    parcel_id: Mapped[str] = mapped_column(String(30), nullable=False)

    # ------------------------------------------------------------------ #
    # Transaction                                                          #
    # ------------------------------------------------------------------ #
    sale_date: Mapped[date | None] = mapped_column(Date)
    sale_price: Mapped[int | None] = mapped_column(Integer)
    instrument_type: Mapped[str | None] = mapped_column(String(10))
    # WD = Warranty Deed, QD = Quit Claim, LD = Limited Warranty,
    # CT = Certificate (tax deed), TD = Tax Deed, PB = Probate

    qualification_code: Mapped[str | None] = mapped_column(String(5))
    # Q = qualified arm's-length, U = unqualified, M = multi-parcel, etc.

    sale_type: Mapped[str | None] = mapped_column(String(5))
    # I = improved, V = vacant, etc.

    multi_parcel: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # ------------------------------------------------------------------ #
    # Parties                                                              #
    # ------------------------------------------------------------------ #
    grantor: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    grantee: Mapped[str] = mapped_column(String(300), nullable=False, default="")

    # ------------------------------------------------------------------ #
    # Derived — computed at ingest, not query time                        #
    # ------------------------------------------------------------------ #
    price_per_sqft: Mapped[float | None] = mapped_column(Numeric(8, 2))
    # Populated only when sale_price > 0 and tot_lvg_area is known

    # ------------------------------------------------------------------ #
    # Provenance                                                           #
    # ------------------------------------------------------------------ #
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    # e.g. 'srcpa_parcelview', 'escpa_cama'

    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
