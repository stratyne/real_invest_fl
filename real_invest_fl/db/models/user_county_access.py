"""
UserCountyAccess — join table granting a user access to a county.

Superusers bypass this table entirely (enforced in the dependency layer).
Regular users must have a row here for each county they may access.
granted_by_user_id is NULL for system-seeded grants (first superuser).
"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import Integer, String, ForeignKey, DateTime, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from real_invest_fl.db.base import Base


class UserCountyAccess(Base):
    __tablename__ = "user_county_access"
    __table_args__ = (
        UniqueConstraint("user_id", "county_fips", name="uq_user_county"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    county_fips: Mapped[str] = mapped_column(
        String(5), ForeignKey("counties.county_fips"), nullable=False
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    granted_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    user: Mapped[User] = relationship(
        "User", back_populates="county_access", foreign_keys=[user_id]
    )
