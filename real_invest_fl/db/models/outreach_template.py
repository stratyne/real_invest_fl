"""
OutreachTemplate - versioned Jinja2 outreach message templates.

Mirrors the system/user ownership pattern of FilterProfile exactly.
System templates: user_id IS NULL - visible to all authorized users,
not editable or deletable by users.
User templates: user_id = owner - private, cloneable from system templates.

county_fips nullable: NULL = global template (available across all counties
the user has access to). Non-NULL = county-scoped template.

template_type domain: EMAIL | LETTER - enforced by CHECK constraint.
subject_template is nullable and applies to EMAIL templates only.
LETTER templates have no subject line.

Partial unique indexes (mirrors filter_profiles pattern):
  uq_ot_system_name  - UNIQUE (template_name) WHERE user_id IS NULL
  uq_ot_user_name    - UNIQUE (user_id, template_name) WHERE user_id IS NOT NULL
"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import (
    String, Integer, Boolean, DateTime, Text,
    ForeignKey, Index, CheckConstraint, func
)
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from real_invest_fl.db.base import Base


class OutreachTemplate(Base):
    __tablename__ = "outreach_templates"
    __table_args__ = (
        CheckConstraint(
            "template_type IN ('EMAIL', 'LETTER')",
            name="chk_ot_template_type",
        ),
        Index(
            "uq_ot_system_name",
            "template_name",
            unique=True,
            postgresql_where=sa_text("user_id IS NULL"),
        ),
        Index(
            "uq_ot_user_name",
            "user_id",
            "template_name",
            unique=True,
            postgresql_where=sa_text("user_id IS NOT NULL"),
        ),
        Index("ix_ot_user_id",       "user_id"),
        Index("ix_ot_template_type", "template_type"),
    )

    # ------------------------------------------------------------------ #
    # Primary key                                                          #
    # ------------------------------------------------------------------ #
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ------------------------------------------------------------------ #
    # Ownership - NULL = system template                                   #
    # ------------------------------------------------------------------ #
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL", name="fk_ot_user_id"),
        nullable=True,
    )

    # ------------------------------------------------------------------ #
    # Scope - NULL = global (all counties user has access to)             #
    # ------------------------------------------------------------------ #
    county_fips: Mapped[str | None] = mapped_column(String(5), nullable=True)

    # ------------------------------------------------------------------ #
    # Identity                                                             #
    # ------------------------------------------------------------------ #
    template_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description:   Mapped[str | None] = mapped_column(Text, nullable=True)

    # ------------------------------------------------------------------ #
    # Template type - EMAIL | LETTER (CHECK constraint above)             #
    # ------------------------------------------------------------------ #
    template_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # ------------------------------------------------------------------ #
    # Content                                                              #
    # ------------------------------------------------------------------ #
    subject_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    # EMAIL only - NULL for LETTER templates

    body_template: Mapped[str] = mapped_column(Text, nullable=False)

    # ------------------------------------------------------------------ #
    # State                                                                #
    # ------------------------------------------------------------------ #
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

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
    owner: Mapped[User | None] = relationship(
        "User",
        back_populates="outreach_templates",
        foreign_keys="[OutreachTemplate.user_id]",
    )
    outreach_logs: Mapped[list[OutreachLog]] = relationship(
        "OutreachLog",
        back_populates="template",
        foreign_keys="[OutreachLog.template_id]",
        # RESTRICT on delete - no cascade. Template cannot be deleted while
        # log rows reference it. Enforced at DB level; relationship carries
        # no cascade here to match that intent.
    )
