"""
User — platform account. Authenticated via JWT (OAuth2 password flow).

is_superuser bypasses all county access checks in the dependency layer.
Passwords are stored as bcrypt hashes via passlib — never plaintext.
"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from real_invest_fl.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False
    )

    # Relationships
    county_access: Mapped[list[UserCountyAccess]] = relationship(
        "UserCountyAccess",
        back_populates="user",
        foreign_keys="[UserCountyAccess.user_id]",
        cascade="all, delete-orphan",
    )
    filter_profiles: Mapped[list[FilterProfile]] = relationship(
        "FilterProfile",
        back_populates="owner",
        foreign_keys="[FilterProfile.user_id]",
    )
