"""ingest_runs v0.6 — full implementation

Revision ID: 390bc7eab733
Revises: 5381f80387ed
Create Date: 2026-04-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '390bc7eab733'
down_revision = '5381f80387ed'
branch_labels = None
depends_on = None


def upgrade() -> None:

    # ------------------------------------------------------------------ #
    # SECTION 1 — Drop the stubbed ingest_runs table                      #
    # ------------------------------------------------------------------ #
    op.drop_table('ingest_runs')

    # ------------------------------------------------------------------ #
    # SECTION 2 — Recreate ingest_runs fully implemented                  #
    # ------------------------------------------------------------------ #
    op.create_table('ingest_runs',

        # Identity
        sa.Column('id',
                  sa.Integer(),
                  autoincrement=True,
                  nullable=False),
        sa.Column('run_type',
                  sa.String(length=30),
                  nullable=False),
        sa.Column('county_fips',
                  sa.String(length=5),
                  nullable=False),
        sa.Column('source_file',
                  sa.String(length=500),
                  nullable=True),
        sa.Column('run_status',
                  sa.String(length=20),
                  nullable=False),

        # Timing
        sa.Column('started_at',
                  sa.DateTime(timezone=True),
                  nullable=False),
        sa.Column('completed_at',
                  sa.DateTime(timezone=True),
                  nullable=True),
        sa.Column('duration_seconds',
                  sa.Integer(),
                  nullable=True),

        # Volume counters
        sa.Column('records_read',
                  sa.Integer(),
                  nullable=True),
        sa.Column('records_inserted',
                  sa.Integer(),
                  nullable=True),
        sa.Column('records_updated',
                  sa.Integer(),
                  nullable=True),
        sa.Column('records_rejected',
                  sa.Integer(),
                  nullable=True),
        sa.Column('records_skipped',
                  sa.Integer(),
                  nullable=True),

        # Quality
        sa.Column('filter_profile_id',
                  sa.Integer(),
                  nullable=True),
        sa.Column('rejection_summary',
                  postgresql.JSONB(astext_type=sa.Text()),
                  nullable=True),
        sa.Column('error_message',
                  sa.Text(),
                  nullable=True),
        sa.Column('error_traceback',
                  sa.Text(),
                  nullable=True),

        # Audit
        sa.Column('created_at',
                  sa.DateTime(timezone=True),
                  server_default=sa.text('now()'),
                  nullable=False),

        sa.PrimaryKeyConstraint('id'),
    )

    # ------------------------------------------------------------------ #
    # SECTION 3 — Indexes                                                  #
    # ------------------------------------------------------------------ #
    op.create_index('ix_ingest_runs_county_fips',
                    'ingest_runs', ['county_fips'], unique=False)
    op.create_index('ix_ingest_runs_run_type',
                    'ingest_runs', ['run_type'],    unique=False)
    op.create_index('ix_ingest_runs_started_at',
                    'ingest_runs', ['started_at'],  unique=False)
    op.create_index('ix_ingest_runs_run_status',
                    'ingest_runs', ['run_status'],  unique=False)


def downgrade() -> None:

    op.drop_index('ix_ingest_runs_run_status',  table_name='ingest_runs')
    op.drop_index('ix_ingest_runs_started_at',  table_name='ingest_runs')
    op.drop_index('ix_ingest_runs_run_type',    table_name='ingest_runs')
    op.drop_index('ix_ingest_runs_county_fips', table_name='ingest_runs')
    op.drop_table('ingest_runs')

    # Restore stub
    op.create_table('ingest_runs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
