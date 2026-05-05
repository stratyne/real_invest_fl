"""v0.17 — Phase 4 outreach schema

outreach_log existed as a stub (id, user_id only) from v0.13.
This migration alters the stub to its full design rather than
creating it from scratch.

outreach_templates and skip_trace_cache are new — CREATE TABLE.

users.calendar_link is new — ADD COLUMN.

fk_ol_user_id on outreach_log was SET NULL in v0.13 stub.
Corrected to CASCADE here — DROP and recreate.

Revision ID: j1k2l3m4n5o6
Revises: i0j1k2l3m4n5
Create Date: 2026-05-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'j1k2l3m4n5o6'
down_revision = 'i0j1k2l3m4n5'
branch_labels = None
depends_on = None


def upgrade() -> None:

    # ------------------------------------------------------------------ #
    # users — add calendar_link                                            #
    # ------------------------------------------------------------------ #
    op.add_column(
        "users",
        sa.Column("calendar_link", sa.String(1000), nullable=True),
    )

    # ------------------------------------------------------------------ #
    # outreach_templates (new table)                                       #
    # ------------------------------------------------------------------ #
    op.create_table(
        "outreach_templates",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("county_fips", sa.String(5), nullable=True),
        sa.Column("template_name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "template_type",
            sa.String(50),
            nullable=False,
            comment="EMAIL | LETTER",
        ),
        sa.Column("subject_template", sa.Text(), nullable=True),
        sa.Column("body_template", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="outreach_templates_pkey"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_ot_user_id",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "template_type IN ('EMAIL', 'LETTER')",
            name="chk_ot_template_type",
        ),
    )
    op.create_index(
        "uq_ot_system_name",
        "outreach_templates",
        ["template_name"],
        unique=True,
        postgresql_where=sa.text("user_id IS NULL"),
    )
    op.create_index(
        "uq_ot_user_name",
        "outreach_templates",
        ["user_id", "template_name"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    op.create_index("ix_ot_user_id", "outreach_templates", ["user_id"])
    op.create_index("ix_ot_template_type", "outreach_templates", ["template_type"])

    # ------------------------------------------------------------------ #
    # skip_trace_cache (new table)                                         #
    # ------------------------------------------------------------------ #
    op.create_table(
        "skip_trace_cache",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("county_fips", sa.String(5), nullable=False),
        sa.Column("parcel_id", sa.String(30), nullable=False),
        sa.Column("skip_trace_result", JSONB(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "provider",
            sa.String(50),
            nullable=False,
            server_default="BATCHDATA",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="skip_trace_cache_pkey"),
    )
    op.create_index(
        "uq_stc_county_parcel",
        "skip_trace_cache",
        ["county_fips", "parcel_id"],
        unique=True,
    )
    op.create_index("ix_stc_expires_at", "skip_trace_cache", ["expires_at"])

    # ------------------------------------------------------------------ #
    # outreach_log — alter stub to full schema                             #
    # ------------------------------------------------------------------ #

    # Drop the v0.13 stub FK — was SET NULL, must be CASCADE
    op.drop_constraint("fk_ol_user_id", "outreach_log", type_="foreignkey")

    # Add all missing columns
    op.add_column("outreach_log",
        sa.Column("county_fips", sa.String(5), nullable=False,
                server_default="00000"))
    op.add_column("outreach_log",
        sa.Column("parcel_id", sa.String(30), nullable=False,
                  server_default="PENDING"))
    op.add_column("outreach_log",
        sa.Column("listing_event_id", sa.Integer(), nullable=False,
                  server_default="0"))
    op.add_column("outreach_log",
        sa.Column("filter_profile_id", sa.Integer(), nullable=True))
    op.add_column("outreach_log",
        sa.Column("template_id", sa.Integer(), nullable=False,
                  server_default="0"))
    op.add_column("outreach_log",
        sa.Column("listing_score_id", sa.Integer(), nullable=True))
    op.add_column("outreach_log",
        sa.Column("recipient_name", sa.String(200), nullable=True))
    op.add_column("outreach_log",
        sa.Column("recipient_email", sa.String(255), nullable=True))
    op.add_column("outreach_log",
        sa.Column("recipient_phone", sa.String(30), nullable=True))
    op.add_column("outreach_log",
        sa.Column("recipient_address1", sa.String(200), nullable=True))
    op.add_column("outreach_log",
        sa.Column("recipient_address2", sa.String(200), nullable=True))
    op.add_column("outreach_log",
        sa.Column("recipient_city", sa.String(100), nullable=True))
    op.add_column("outreach_log",
        sa.Column("recipient_state", sa.String(25), nullable=True))
    op.add_column("outreach_log",
        sa.Column("recipient_zip", sa.String(10), nullable=True))
    op.add_column("outreach_log",
        sa.Column("skip_trace_result", JSONB(), nullable=True))
    op.add_column("outreach_log",
        sa.Column("message_subject", sa.String(500), nullable=True))
    op.add_column("outreach_log",
        sa.Column("message_body", sa.Text(), nullable=True))
    op.add_column("outreach_log",
        sa.Column("calendar_link", sa.String(1000), nullable=True))
    op.add_column("outreach_log",
        sa.Column(
            "template_type",
            sa.String(50),
            nullable=False,
            server_default="EMAIL",
            comment="EMAIL | LETTER — snapshot from outreach_templates row",
        ))
    op.add_column("outreach_log",
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="DRAFT",
            comment="DRAFT | SENT | FAILED",
        ))
    op.add_column("outreach_log",
        sa.Column("sent_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("outreach_log",
        sa.Column("send_error", sa.Text(), nullable=True))
    op.add_column("outreach_log",
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ))
    op.add_column("outreach_log",
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ))

    # Drop server_defaults that were only needed to satisfy NOT NULL
    # on ALTER — these columns must not carry permanent defaults
    op.alter_column("outreach_log", "county_fips", server_default=None)
    op.alter_column("outreach_log", "parcel_id", server_default=None)
    op.alter_column("outreach_log", "listing_event_id", server_default=None)
    op.alter_column("outreach_log", "template_id", server_default=None)
    op.alter_column("outreach_log", "template_type", server_default=None)

    # Recreate fk_ol_user_id as CASCADE
    op.create_foreign_key(
        "fk_ol_user_id", "outreach_log",
        "users", ["user_id"], ["id"],
        ondelete="CASCADE",
    )

    # Remaining FKs
    op.create_foreign_key(
        "fk_ol_listing_event_id", "outreach_log",
        "listing_events", ["listing_event_id"], ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_ol_filter_profile_id", "outreach_log",
        "filter_profiles", ["filter_profile_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_ol_template_id", "outreach_log",
        "outreach_templates", ["template_id"], ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_ol_listing_score_id", "outreach_log",
        "listing_scores", ["listing_score_id"], ["id"],
        ondelete="SET NULL",
    )

    # CHECK constraints
    op.create_check_constraint(
        "chk_ol_template_type", "outreach_log",
        "template_type IN ('EMAIL', 'LETTER')",
    )
    op.create_check_constraint(
        "chk_ol_status", "outreach_log",
        "status IN ('DRAFT', 'SENT', 'FAILED')",
    )

    # Indexes
    op.create_index("ix_ol_county_user", "outreach_log",
                    ["county_fips", "user_id"])
    op.create_index("ix_ol_listing_event", "outreach_log",
                    ["listing_event_id"])
    op.create_index("ix_ol_status", "outreach_log", ["status"])
    op.create_index("ix_ol_parcel", "outreach_log",
                    ["county_fips", "parcel_id"])


def downgrade() -> None:

    # ------------------------------------------------------------------ #
    # outreach_log — return to v0.13 stub state                           #
    # ------------------------------------------------------------------ #
    op.drop_index("ix_ol_parcel", table_name="outreach_log")
    op.drop_index("ix_ol_status", table_name="outreach_log")
    op.drop_index("ix_ol_listing_event", table_name="outreach_log")
    op.drop_index("ix_ol_county_user", table_name="outreach_log")

    op.drop_constraint("chk_ol_status", "outreach_log", type_="check")
    op.drop_constraint("chk_ol_template_type", "outreach_log", type_="check")

    op.drop_constraint("fk_ol_listing_score_id", "outreach_log",
                       type_="foreignkey")
    op.drop_constraint("fk_ol_template_id", "outreach_log",
                       type_="foreignkey")
    op.drop_constraint("fk_ol_filter_profile_id", "outreach_log",
                       type_="foreignkey")
    op.drop_constraint("fk_ol_listing_event_id", "outreach_log",
                       type_="foreignkey")
    op.drop_constraint("fk_ol_user_id", "outreach_log", type_="foreignkey")

    op.drop_column("outreach_log", "updated_at")
    op.drop_column("outreach_log", "created_at")
    op.drop_column("outreach_log", "send_error")
    op.drop_column("outreach_log", "sent_at")
    op.drop_column("outreach_log", "status")
    op.drop_column("outreach_log", "template_type")
    op.drop_column("outreach_log", "calendar_link")
    op.drop_column("outreach_log", "message_body")
    op.drop_column("outreach_log", "message_subject")
    op.drop_column("outreach_log", "skip_trace_result")
    op.drop_column("outreach_log", "recipient_zip")
    op.drop_column("outreach_log", "recipient_state")
    op.drop_column("outreach_log", "recipient_city")
    op.drop_column("outreach_log", "recipient_address2")
    op.drop_column("outreach_log", "recipient_address1")
    op.drop_column("outreach_log", "recipient_phone")
    op.drop_column("outreach_log", "recipient_email")
    op.drop_column("outreach_log", "recipient_name")
    op.drop_column("outreach_log", "listing_score_id")
    op.drop_column("outreach_log", "template_id")
    op.drop_column("outreach_log", "filter_profile_id")
    op.drop_column("outreach_log", "listing_event_id")
    op.drop_column("outreach_log", "parcel_id")
    op.drop_column("outreach_log", "county_fips")

    # Restore v0.13 FK — SET NULL
    op.create_foreign_key(
        "fk_ol_user_id", "outreach_log",
        "users", ["user_id"], ["id"],
        ondelete="SET NULL",
    )

    # ------------------------------------------------------------------ #
    # skip_trace_cache                                                     #
    # ------------------------------------------------------------------ #
    op.drop_index("ix_stc_expires_at", table_name="skip_trace_cache")
    op.drop_index("uq_stc_county_parcel", table_name="skip_trace_cache")
    op.drop_table("skip_trace_cache")

    # ------------------------------------------------------------------ #
    # outreach_templates                                                   #
    # ------------------------------------------------------------------ #
    op.drop_index("ix_ot_template_type", table_name="outreach_templates")
    op.drop_index("ix_ot_user_id", table_name="outreach_templates")
    op.drop_index("uq_ot_user_name", table_name="outreach_templates")
    op.drop_index("uq_ot_system_name", table_name="outreach_templates")
    op.drop_table("outreach_templates")

    # ------------------------------------------------------------------ #
    # users                                                                #
    # ------------------------------------------------------------------ #
    op.drop_column("users", "calendar_link")
