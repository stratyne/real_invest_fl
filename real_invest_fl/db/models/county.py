"""
County registry and ZIP code tables.
county_fips is the standard 5-digit FIPS code (e.g., '12033' for Escambia).
dor_county_no is the 2-digit DOR code used in the NAL file (e.g., 28).
"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from real_invest_fl.db.base import Base


class County(Base):
    __tablename__ = "counties"

    county_fips: Mapped[str] = mapped_column(String(5), primary_key=True)
    dor_county_no: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    county_name: Mapped[str] = mapped_column(String(100), nullable=False)
    state_abbr: Mapped[str] = mapped_column(String(2), nullable=False, default="FL")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    poc_county: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Ingest tracking
    nal_last_ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sdf_last_ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cama_last_ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    nal_file_path: Mapped[str | None] = mapped_column(String(500))
    sdf_file_path: Mapped[str | None] = mapped_column(String(500))
    cama_file_path: Mapped[str | None] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False
    )

    # Relationships
    zip_codes: Mapped[list[CountyZip]] = relationship(
        "CountyZip", back_populates="county", cascade="all, delete-orphan"
    )


class CountyZip(Base):
    __tablename__ = "county_zips"
    __table_args__ = (UniqueConstraint("county_fips", "zip_code", name="uq_county_zip"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from sqlalchemy import ForeignKey

    county_fips: Mapped[str] = mapped_column(
        String(5), ForeignKey("counties.county_fips"), nullable=False
    )
    zip_code: Mapped[str] = mapped_column(String(10), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    county: Mapped[County] = relationship("County", back_populates="zip_codes")
