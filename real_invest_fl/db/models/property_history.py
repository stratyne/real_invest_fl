"""
PropertyValueHistory — append-only log of assessed/just values per parcel/year.
Never updated; new row inserted each annual NAL refresh.
"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from real_invest_fl.db.base import Base


class PropertyValueHistory(Base):
    __tablename__ = "property_value_history"
    __table_args__ = (
        Index("ix_pvh_county_parcel", "county_fips", "parcel_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    county_fips: Mapped[str] = mapped_column(String(5), nullable=False)
    parcel_id: Mapped[str] = mapped_column(String(30), nullable=False)
    assessment_year: Mapped[int] = mapped_column(Integer, nullable=False)
    just_value: Mapped[int | None] = mapped_column(Integer)
    assessed_value: Mapped[int | None] = mapped_column(Integer)
    taxable_value: Mapped[int | None] = mapped_column(Integer)

    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    property: Mapped[Property] = relationship(
        "Property",
        back_populates="value_history",
        primaryjoin="and_(PropertyValueHistory.county_fips==Property.county_fips, "
                    "PropertyValueHistory.parcel_id==Property.parcel_id)",
        foreign_keys="[PropertyValueHistory.county_fips, PropertyValueHistory.parcel_id]",
    )
