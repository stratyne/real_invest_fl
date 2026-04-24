"""
SalesComp — populated from the DOR Sale Data File (SDF).
Powers the internal ARV comp engine; replaces Zestimate as primary signal.
One row per qualified arm's-length sale.
"""
from __future__ import annotations
from datetime import datetime, date
from sqlalchemy import String, Integer, Boolean, DateTime, Date, Numeric, Index, func
from sqlalchemy.orm import Mapped, mapped_column
from real_invest_fl.db.base import Base


class SalesComp(Base):
    __tablename__ = "sales_comps"
    __table_args__ = (
        Index("ix_sc_county_zip_year", "county_fips", "zip_code", "actual_year_built"),
        Index("ix_sc_sale_date", "sale_date"),
        Index("ix_sc_dor_use_code", "dor_use_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    county_fips: Mapped[str] = mapped_column(String(5), nullable=False)
    parcel_id: Mapped[str] = mapped_column(String(30), nullable=False)

    # Sale data (from SDF)
    sale_price: Mapped[int | None] = mapped_column(Integer)
    sale_date: Mapped[date | None] = mapped_column(Date)
    sale_qualifier: Mapped[str | None] = mapped_column(String(10))
    # SDF qualifier codes — only arm's-length (qualifier='Q') ingested

    # Property characteristics at time of sale (joined from NAL)
    dor_use_code: Mapped[str | None] = mapped_column(String(10))
    construction_class: Mapped[int | None] = mapped_column(Integer)
    actual_year_built: Mapped[int | None] = mapped_column(Integer)
    total_living_area: Mapped[int | None] = mapped_column(Integer)
    zip_code: Mapped[str | None] = mapped_column(String(10))
    situs_address: Mapped[str | None] = mapped_column(String(300))

    # Derived
    price_per_sqft: Mapped[float | None] = mapped_column(Numeric(8, 2))
    arm_length_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    sdf_ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
