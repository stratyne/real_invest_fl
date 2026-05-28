"""v0.21 — add arv_source to properties

Revision ID: n5o6p7q8r9s0
Revises: m4n5o6p7q8r9
Create Date: 2026-05-26
"""
from alembic import op
import sqlalchemy as sa

revision = "n5o6p7q8r9s0"
down_revision = "m4n5o6p7q8r9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "properties",
        sa.Column("arv_source", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("properties", "arv_source")
