"""widen own_state from VARCHAR(2) to VARCHAR(25)

Revision ID: a1b2c3d4e5f6
Revises: 25a1f5163f3b
Create Date: 2026-04-26

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '25a1f5163f3b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # DOR NAL field 78 (OWN_STATE) is variable length, max 25.
    # Schema was incorrectly set to VARCHAR(2), causing
    # StringDataRightTruncationError on international owner addresses
    # (e.g. "CANADA", "UNITED KINGDOM").
    op.alter_column(
        'properties',
        'own_state',
        existing_type=sa.String(2),
        type_=sa.String(25),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        'properties',
        'own_state',
        existing_type=sa.String(25),
        type_=sa.String(2),
        existing_nullable=True,
    )
