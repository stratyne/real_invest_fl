"""v0_9_arv_columns

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-27

Adds four ARV and listing columns to the properties table:
    - jv_per_sqft         : Just Value per square foot (JV / tot_lvg_area)
    - arv_estimate        : ARV proxy — mirrors jv now, replaceable by SDF comp engine later
    - arv_spread          : arv_estimate minus list_price (populated in Phase 2)
    - list_price          : Scraped list price from Phase 2 listing events
"""

from alembic import op
import sqlalchemy as sa

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------
revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("properties", sa.Column("jv_per_sqft",    sa.Numeric(), nullable=True))
    op.add_column("properties", sa.Column("arv_estimate",   sa.Integer(), nullable=True))
    op.add_column("properties", sa.Column("arv_spread",     sa.Integer(), nullable=True))
    op.add_column("properties", sa.Column("list_price",     sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("properties", "list_price")
    op.drop_column("properties", "arv_spread")
    op.drop_column("properties", "arv_estimate")
    op.drop_column("properties", "jv_per_sqft")
