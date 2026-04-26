"""filter_profiles table v0.4 — replace scalar filter columns with
   filter_criteria JSONB; retain engine/operational config columns

Revision ID: f422169456bd
Revises: 4ca6031e21c4
Create Date: 2026-04-25 21:18:36.432112
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'f422169456bd'
down_revision = '4ca6031e21c4'
branch_labels = None
depends_on = None


def upgrade() -> None:

    # ------------------------------------------------------------------ #
    # SECTION 1 — Drop scalar filter dimension columns                    #
    # ------------------------------------------------------------------ #
    op.drop_column('filter_profiles', 'max_list_price')
    op.drop_column('filter_profiles', 'min_list_price')
    op.drop_column('filter_profiles', 'target_beds')
    op.drop_column('filter_profiles', 'target_baths')
    op.drop_column('filter_profiles', 'min_year_built')
    op.drop_column('filter_profiles', 'primary_max_year_built')
    op.drop_column('filter_profiles', 'min_arv_spread')
    op.drop_column('filter_profiles', 'min_zestimate_discount_pct')
    op.drop_column('filter_profiles', 'zestimate_staleness_days')
    op.drop_column('filter_profiles', 'allowed_dor_use_codes')
    op.drop_column('filter_profiles', 'allowed_construction_classes')
    op.drop_column('filter_profiles', 'allowed_foundation_keywords')
    op.drop_column('filter_profiles', 'disallowed_foundation_keywords')
    op.drop_column('filter_profiles', 'allowed_construction_keywords')
    op.drop_column('filter_profiles', 'disallowed_property_types')

    # ------------------------------------------------------------------ #
    # SECTION 2 — Add filter_criteria JSONB column                        #
    # ------------------------------------------------------------------ #
    op.add_column('filter_profiles',
        sa.Column('filter_criteria',
                  postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False,
                  server_default='{}'))

    # Remove server_default after adding — it was only needed to satisfy
    # NOT NULL for the ALTER TABLE. Production rows will always be seeded
    # with a complete filter_criteria document.
    op.alter_column('filter_profiles', 'filter_criteria', server_default=None)


def downgrade() -> None:

    # Drop filter_criteria
    op.drop_column('filter_profiles', 'filter_criteria')

    # Restore scalar filter dimension columns
    op.add_column('filter_profiles',
        sa.Column('max_list_price', sa.Integer(), nullable=False, server_default='225000'))
    op.add_column('filter_profiles',
        sa.Column('min_list_price', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('filter_profiles',
        sa.Column('target_beds', sa.Integer(), nullable=False, server_default='3'))
    op.add_column('filter_profiles',
        sa.Column('target_baths', sa.Integer(), nullable=False, server_default='2'))
    op.add_column('filter_profiles',
        sa.Column('min_year_built', sa.Integer(), nullable=False, server_default='1950'))
    op.add_column('filter_profiles',
        sa.Column('primary_max_year_built', sa.Integer(), nullable=False, server_default='1960'))
    op.add_column('filter_profiles',
        sa.Column('min_arv_spread', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('filter_profiles',
        sa.Column('min_zestimate_discount_pct', sa.Float(), nullable=False, server_default='0.0'))
    op.add_column('filter_profiles',
        sa.Column('zestimate_staleness_days', sa.Integer(), nullable=False, server_default='7'))
    op.add_column('filter_profiles',
        sa.Column('allowed_dor_use_codes',
                  postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, server_default='["001"]'))
    op.add_column('filter_profiles',
        sa.Column('allowed_construction_classes',
                  postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, server_default='[3]'))
    op.add_column('filter_profiles',
        sa.Column('allowed_foundation_keywords',
                  postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, server_default='[]'))
    op.add_column('filter_profiles',
        sa.Column('disallowed_foundation_keywords',
                  postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, server_default='[]'))
    op.add_column('filter_profiles',
        sa.Column('allowed_construction_keywords',
                  postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, server_default='[]'))
    op.add_column('filter_profiles',
        sa.Column('disallowed_property_types',
                  postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, server_default='[]'))
