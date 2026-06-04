"""
UserProfilePrefs - per-user activity and preference state for a filter profile.

Tracks whether the user has favorited a profile, when they last ran it,
how many results it returned, and how many times they have run it total.

Used by:
  routes/dashboard.py  - get_dashboard (favorite profiles + recent activity)
  routes/profiles.py   - toggle_favorite
  routes/properties.py - search_properties (upsert on run)

One row per (user_id, profile_id) pair - enforced by uq_upp_user_profile.
"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from real_invest_fl.db.base import Base


class UserProfilePrefs(Base):
    __tablename__ = "user_profile_prefs"

    # ------------------------------------------------------------------ #
    # Identity                                                             #
    # ------------------------------------------------------------------ #
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ------------------------------------------------------------------ #
    # Ownership                                                            #
    # ------------------------------------------------------------------ #
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    profile_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("filter_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )

    # ------------------------------------------------------------------ #
    # Preference and activity state                                        #
    # ------------------------------------------------------------------ #
    is_favorite: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    last_searched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_result_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    run_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    # ------------------------------------------------------------------ #
    # Audit                                                                #
    # ------------------------------------------------------------------ #
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False
    )

    # ------------------------------------------------------------------ #
    # Relationships                                                        #
    # ------------------------------------------------------------------ #
    user: Mapped[User] = relationship(
        "User",
        back_populates="profile_prefs",
        foreign_keys=[user_id],
    )
    profile: Mapped[FilterProfile] = relationship(
        "FilterProfile",
        back_populates="user_prefs",
        foreign_keys=[profile_id],
    )
