"""
OutreachLog — lifecycle record for each outreach message.

One row is written per generate_outreach call (DRAFT status).
send_outreach updates the same row to SENT or FAILED — draft and sent
state live on the same row. sent_at NULL means the message has not been sent.

status domain: DRAFT | SENT | FAILED — enforced by CHECK constraint.
template_type domain: EMAIL | LETTER — snapshot of outreach_templates.template_type
at generate time, enforced by CHECK constraint.

Snapshot pattern: recipient fields, calendar_link, skip_trace_result, and
template_type are all snapshotted from their source rows at generate time.
The audit record is self-contained regardless of subsequent changes to the
source data.

Cascade rules:
  user_id:           CASCADE  — deleted user's log goes with them
  listing_event_id:  CASCADE  — no orphaned log rows
  filter_profile_id: SET NULL — deleted profile orphans the row gracefully;
                                audit record preserved
  template_id:       RESTRICT — template cannot be deleted while log rows
                                reference it; preserves audit trail
  listing_score_id:  SET NULL — log row preserved if score row is deleted
"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import (
    String, Integer, DateTime, Text,
    ForeignKey, Index, CheckConstraint, func
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from real_invest_fl.db.base import Base


class OutreachLog(Base):
    __tablename__ = "outreach_log"
    __table_args__ = (
        CheckConstraint(
            "template_type IN ('EMAIL', 'LETTER')",
            name="chk_ol_template_type",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'SENT', 'FAILED')",
            name="chk_ol_status",
        ),
        Index("ix_ol_county_user",    "county_fips", "user_id"),
        Index("ix_ol_listing_event",  "listing_event_id"),
        Index("ix_ol_status",         "status"),
        Index("ix_ol_parcel",         "county_fips", "parcel_id"),
    )

    # ------------------------------------------------------------------ #
    # Primary key                                                          #
    # ------------------------------------------------------------------ #
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ------------------------------------------------------------------ #
    # Scope                                                                #
    # ------------------------------------------------------------------ #
    county_fips: Mapped[str] = mapped_column(String(5),  nullable=False)
    parcel_id:   Mapped[str] = mapped_column(String(30), nullable=False)

    # ------------------------------------------------------------------ #
    # Foreign keys                                                         #
    # ------------------------------------------------------------------ #
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE", name="fk_ol_user_id"),
        nullable=True,
        # nullable inherited from v0.13 stub; application layer always populates
    )
    listing_event_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("listing_events.id", ondelete="CASCADE", name="fk_ol_listing_event_id"),
        nullable=False,
    )
    filter_profile_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("filter_profiles.id", ondelete="SET NULL", name="fk_ol_filter_profile_id"),
        nullable=True,
    )
    template_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("outreach_templates.id", ondelete="RESTRICT", name="fk_ol_template_id"),
        nullable=False,
    )
    listing_score_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("listing_scores.id", ondelete="SET NULL", name="fk_ol_listing_score_id"),
        nullable=True,
    )

    # ------------------------------------------------------------------ #
    # Recipient snapshot — populated at generate time from properties     #
    # and skip_trace_cache. Self-contained audit record.                  #
    # ------------------------------------------------------------------ #
    recipient_name:     Mapped[str | None] = mapped_column(String(200), nullable=True)
    recipient_email:    Mapped[str | None] = mapped_column(String(255), nullable=True)
    recipient_phone:    Mapped[str | None] = mapped_column(String(30),  nullable=True)
    recipient_address1: Mapped[str | None] = mapped_column(String(200), nullable=True)
    recipient_address2: Mapped[str | None] = mapped_column(String(200), nullable=True)
    recipient_city:     Mapped[str | None] = mapped_column(String(100), nullable=True)
    recipient_state:    Mapped[str | None] = mapped_column(String(25),  nullable=True)
    recipient_zip:      Mapped[str | None] = mapped_column(String(10),  nullable=True)

    # ------------------------------------------------------------------ #
    # Skip-trace snapshot — NULL if no non-expired cache row at generate  #
    # ------------------------------------------------------------------ #
    skip_trace_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # ------------------------------------------------------------------ #
    # Message content                                                      #
    # ------------------------------------------------------------------ #
    message_subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # NULL for LETTER template_type

    message_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Populated by Jinja2 render at generate time.
    # send_outreach guards NOT NULL before sending.

    # ------------------------------------------------------------------ #
    # Booking link snapshot — from users.calendar_link at generate time   #
    # NULL if user has not set calendar_link                               #
    # ------------------------------------------------------------------ #
    calendar_link: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # ------------------------------------------------------------------ #
    # Template type snapshot — EMAIL | LETTER (CHECK constraint above)    #
    # ------------------------------------------------------------------ #
    template_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # ------------------------------------------------------------------ #
    # Status — DRAFT | SENT | FAILED (CHECK constraint above)             #
    # ------------------------------------------------------------------ #
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="DRAFT"
    )

    # ------------------------------------------------------------------ #
    # Send outcome                                                         #
    # ------------------------------------------------------------------ #
    sent_at:    Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    send_error: Mapped[str | None]      = mapped_column(Text, nullable=True)

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
    user: Mapped[User | None] = relationship(
        "User",
        back_populates="outreach_logs",
        foreign_keys="[OutreachLog.user_id]",
    )
    listing_event: Mapped[ListingEvent] = relationship(
        "ListingEvent",
        back_populates="outreach_logs",
        foreign_keys="[OutreachLog.listing_event_id]",
    )
    filter_profile: Mapped[FilterProfile | None] = relationship(
        "FilterProfile",
        back_populates="outreach_logs",
        foreign_keys="[OutreachLog.filter_profile_id]",
    )
    template: Mapped[OutreachTemplate] = relationship(
        "OutreachTemplate",
        back_populates="outreach_logs",
        foreign_keys="[OutreachLog.template_id]",
    )
    listing_score: Mapped[ListingScore | None] = relationship(
        "ListingScore",
        back_populates="outreach_log",
        foreign_keys="[OutreachLog.listing_score_id]",
    )
