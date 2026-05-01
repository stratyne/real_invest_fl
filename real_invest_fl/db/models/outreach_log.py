"""
OutreachLog — append-only outreach record.

Full schema (listing_event_id, channel, sent_at, status, etc.)
is Phase 4 scope. user_id added now to avoid mid-Phase-4 migration.
"""
from __future__ import annotations
from sqlalchemy import Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from real_invest_fl.db.base import Base


class OutreachLog(Base):
    __tablename__ = "outreach_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
