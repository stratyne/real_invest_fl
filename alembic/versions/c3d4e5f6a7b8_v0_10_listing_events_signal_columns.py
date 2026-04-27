"""v0_10_listing_events_signal_columns

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-27

Adds signal classification columns to listing_events table to support
the Phase 2 hybrid signal-aggregator + traditional listing model.

New columns:
    signal_tier  — INTEGER  : Priority tier of the signal source
                              1 = Government distress records (highest signal)
                              2 = Bulk public data / government auction portals
                              3 = Commercial listing platforms / FSBO
    signal_type  — VARCHAR(50) : Semantic type of the signal event
                              Examples: foreclosure_sale, tax_deed, lis_pendens,
                              tax_delinquent, fsbo, active_listing,
                              expired_listing, auction, surplus

These columns coexist with listing_type, which is reserved for MLS-style
listing classification (Active, Pending, Expired, etc.) when that data
is available from a traditional listing source.
"""

from alembic import op
import sqlalchemy as sa

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------
revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "listing_events",
        sa.Column("signal_tier", sa.Integer(), nullable=True),
    )
    op.add_column(
        "listing_events",
        sa.Column("signal_type", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("listing_events", "signal_type")
    op.drop_column("listing_events", "signal_tier")
