"""v0_12_data_source_status

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-01

Adds data_source_status table for UI source health display.
One row per (source, county_fips) pair. Updated in-place on
every ingest run via upsert. Separate from ingest_runs, which
is an append-only audit log.

Composite primary key (source, county_fips) supports imminent
multi-county expansion without schema change.
"""

from alembic import op
import sqlalchemy as sa

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------
revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_source_status",
        sa.Column("source",             sa.String(100),             nullable=False),
        sa.Column("county_fips",        sa.String(5),               nullable=False),
        sa.Column("display_name",       sa.String(200),             nullable=False),
        sa.Column("last_success_at",    sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at",        sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_status",    sa.String(20),              nullable=True),
        sa.Column("last_record_count",  sa.Integer(),               nullable=True),
        sa.Column("last_error_message", sa.Text(),                  nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("source", "county_fips", name="pk_data_source_status"),
    )
    op.create_index(
        "ix_dss_county_fips",
        "data_source_status",
        ["county_fips"],
    )


def downgrade() -> None:
    op.drop_index("ix_dss_county_fips", table_name="data_source_status")
    op.drop_table("data_source_status")
