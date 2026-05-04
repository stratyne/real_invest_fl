"""add listing_scores table; strip scoring columns from listing_events

Revision ID: i0j1k2l3m4n5
Revises: h9i0j1k2l3m4
Create Date: 2026-05-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'i0j1k2l3m4n5'
down_revision = 'h9i0j1k2l3m4'
branch_labels = None
depends_on = None


def upgrade() -> None:

    # ------------------------------------------------------------------ #
    # STEP 1 — NULL out POC artifact filter_profile_id on listing_events  #
    # 347 rows carried filter_profile_id = 1 (escambia_poc system profile #
    # from April 2026 POC scrape runs). No scores were ever written.      #
    # Nulled here before column removal — confirmed safe 2026-05-04.      #
    # ------------------------------------------------------------------ #
    op.execute(
        "UPDATE listing_events SET filter_profile_id = NULL "
        "WHERE filter_profile_id IS NOT NULL"
    )

    # ------------------------------------------------------------------ #
    # STEP 2 — Drop scoring columns from listing_events                   #
    # listing_events is now a pure append-only event log.                 #
    # ------------------------------------------------------------------ #
    op.drop_index('ix_le_deal_score', table_name='listing_events')

    op.drop_column('listing_events', 'filter_profile_id')
    op.drop_column('listing_events', 'passed_filters')
    op.drop_column('listing_events', 'filter_rejection_reasons')
    op.drop_column('listing_events', 'deal_score')
    op.drop_column('listing_events', 'deal_score_version')
    op.drop_column('listing_events', 'deal_score_components')

    # ------------------------------------------------------------------ #
    # STEP 3 — Create listing_scores table                                #
    # One row per (listing_event, filter_profile). Scoring output is      #
    # fully isolated from the event log. Per-user recompute is safe and   #
    # bounded — touches only rows for the affected (user, profile).       #
    # ------------------------------------------------------------------ #
    op.create_table(
        'listing_scores',

        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),

        sa.Column('listing_event_id', sa.Integer(), nullable=False),
        sa.Column('filter_profile_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('county_fips', sa.String(5), nullable=False),

        sa.Column('passed_filters', sa.Boolean(), nullable=True),
        sa.Column('filter_rejection_reasons',
                  postgresql.JSONB(astext_type=sa.Text()), nullable=True),

        sa.Column('deal_score', sa.Numeric(5, 4), nullable=True),
        sa.Column('deal_score_version', sa.String(20), nullable=True),
        sa.Column('deal_score_components',
                  postgresql.JSONB(astext_type=sa.Text()), nullable=True),

        sa.Column('scored_at',
                  sa.DateTime(timezone=True),
                  server_default=sa.func.now(),
                  nullable=False),

        # ---------------------------------------------------------- #
        # Foreign keys                                                #
        # ---------------------------------------------------------- #
        sa.ForeignKeyConstraint(
            ['listing_event_id'], ['listing_events.id'],
            name='fk_ls_listing_event_id',
            ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['filter_profile_id'], ['filter_profiles.id'],
            name='fk_ls_filter_profile_id',
            ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['user_id'], ['users.id'],
            name='fk_ls_user_id',
            ondelete='CASCADE'
        ),

        # ---------------------------------------------------------- #
        # Unique constraint — one score row per event per profile     #
        # Ensures upserts are safe and recompute cannot produce       #
        # duplicate rows.                                             #
        # ---------------------------------------------------------- #
        sa.UniqueConstraint(
            'listing_event_id', 'filter_profile_id',
            name='uq_ls_event_profile'
        ),
    )

    # ------------------------------------------------------------------ #
    # STEP 4 — Indexes on listing_scores                                  #
    # ------------------------------------------------------------------ #

    # Primary query pattern: all scores for a user's profile
    op.create_index(
        'ix_ls_user_profile',
        'listing_scores',
        ['user_id', 'filter_profile_id']
    )

    # Score-ranked retrieval within a county for a user
    op.create_index(
        'ix_ls_user_county_score',
        'listing_scores',
        ['user_id', 'county_fips', 'deal_score']
    )

    # Filter pass/fail retrieval
    op.create_index(
        'ix_ls_passed_filters',
        'listing_scores',
        ['filter_profile_id', 'passed_filters']
    )


def downgrade() -> None:

    # ------------------------------------------------------------------ #
    # Drop listing_scores                                                  #
    # ------------------------------------------------------------------ #
    op.drop_index('ix_ls_passed_filters', table_name='listing_scores')
    op.drop_index('ix_ls_user_county_score', table_name='listing_scores')
    op.drop_index('ix_ls_user_profile', table_name='listing_scores')
    op.drop_table('listing_scores')

    # ------------------------------------------------------------------ #
    # Restore scoring columns on listing_events                           #
    # NOTE: the 347 POC rows that previously carried filter_profile_id=1  #
    # are NOT restored — downgrade returns the column structure only,     #
    # not the data. That data was POC artifact and is intentionally lost. #
    # ------------------------------------------------------------------ #
    op.add_column('listing_events',
        sa.Column('filter_profile_id', sa.Integer(), nullable=True))
    op.add_column('listing_events',
        sa.Column('passed_filters', sa.Boolean(), nullable=True))
    op.add_column('listing_events',
        sa.Column('filter_rejection_reasons',
                  postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('listing_events',
        sa.Column('deal_score', sa.Numeric(5, 4), nullable=True))
    op.add_column('listing_events',
        sa.Column('deal_score_version', sa.String(20), nullable=True))
    op.add_column('listing_events',
        sa.Column('deal_score_components',
                  postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    op.create_index(
        'ix_le_deal_score', 'listing_events', ['deal_score'])
