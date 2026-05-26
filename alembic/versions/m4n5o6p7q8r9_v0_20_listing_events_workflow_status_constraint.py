"""v0.20 — add workflow_status CHECK constraint to listing_events

Revision ID: m4n5o6p7q8r9
Revises: l3m4n5o6p7q8
Create Date: 2026-05-26
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = 'm4n5o6p7q8r9'
down_revision = 'l3m4n5o6p7q8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        'ck_listing_events_workflow_status',
        'listing_events',
        "workflow_status IN ('NEW','REVIEWED','APPROVE_SEND','SENT','RESPONDED','REJECTED','CLOSED')",
    )


def downgrade() -> None:
    op.drop_constraint(
        'ck_listing_events_workflow_status',
        'listing_events',
        type_='check',
    )
