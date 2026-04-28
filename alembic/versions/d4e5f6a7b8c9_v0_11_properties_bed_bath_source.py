"""v0_11_properties_bed_bath_source

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-28

Adds bed_bath_source to properties table to track provenance of
bedrooms/bathrooms values when populated opportunistically from
listing sources (Zillow, Craigslist, etc.) rather than CAMA.

This column is set by any parser or scraper that writes bedrooms/bathrooms
to the master properties record. It is not overwritten if already populated
by a higher-confidence source — that logic lives in the parser layer.
"""

from alembic import op
import sqlalchemy as sa

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------
revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "properties",
        sa.Column("bed_bath_source", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("properties", "bed_bath_source")
