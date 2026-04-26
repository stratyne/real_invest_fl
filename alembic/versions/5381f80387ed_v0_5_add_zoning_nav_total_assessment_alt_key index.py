"""properties v0.5 — add zoning, nav_total_assessment, alt_key index

Revision ID: 5381f80387ed
Revises: f422169456bd
Create Date: 2026-04-26 03:34:16.680379
"""
from alembic import op
import sqlalchemy as sa

revision = '5381f80387ed'
down_revision = 'f422169456bd'
branch_labels = None
depends_on = None


def upgrade() -> None:

    # ------------------------------------------------------------------ #
    # SECTION 1 — Add zoning column                                       #
    # Source: ECPA CAMA web page — not available in NAL                   #
    # Populated during Stage 2 CAMA scrape                                #
    # ------------------------------------------------------------------ #
    op.add_column('properties',
        sa.Column('zoning', sa.String(length=20), nullable=True))

    # ------------------------------------------------------------------ #
    # SECTION 2 — Add nav_total_assessment column                         #
    # Source: NAVN Table N field 6 — total non-ad valorem assessments     #
    # Populated when NAV ingest is built — NULL until then                #
    # ------------------------------------------------------------------ #
    op.add_column('properties',
        sa.Column('nav_total_assessment',
                  sa.Numeric(precision=12, scale=2), nullable=True))

    # ------------------------------------------------------------------ #
    # SECTION 3 — Add index on alt_key                                    #
    # alt_key is the join key between properties and NAV files            #
    # (NAVN.tc_account_no normalized == properties.alt_key)              #
    # ------------------------------------------------------------------ #
    op.create_index('ix_properties_alt_key', 'properties', ['alt_key'],
                    unique=False)


def downgrade() -> None:

    op.drop_index('ix_properties_alt_key', table_name='properties')
    op.drop_column('properties', 'nav_total_assessment')
    op.drop_column('properties', 'zoning')
