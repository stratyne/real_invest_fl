"""v0.15 — parcel_sale_history grantor/grantee NOT NULL DEFAULT ''

NULL grantor/grantee breaks the unique constraint uq_psh_county_parcel_sale
because PostgreSQL treats NULL != NULL in unique indexes. Coercing to
empty string ensures idempotent re-runs via ON CONFLICT DO NOTHING.

Revision ID: h9i0j1k2l3m4
Revises: g8h9i0j1k2l3
Create Date: 2026-05-04
"""
from alembic import op
import sqlalchemy as sa

revision = "h9i0j1k2l3m4"
down_revision = "g8h9i0j1k2l3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1 — coerce any existing NULLs to empty string
    op.execute(
        "UPDATE parcel_sale_history "
        "SET grantor = '' WHERE grantor IS NULL"
    )
    op.execute(
        "UPDATE parcel_sale_history "
        "SET grantee = '' WHERE grantee IS NULL"
    )

    # Step 2 — alter columns to NOT NULL with default ''
    op.alter_column(
        "parcel_sale_history", "grantor",
        existing_type=sa.String(300),
        nullable=False,
        server_default="",
    )
    op.alter_column(
        "parcel_sale_history", "grantee",
        existing_type=sa.String(300),
        nullable=False,
        server_default="",
    )


def downgrade() -> None:
    op.alter_column(
        "parcel_sale_history", "grantee",
        existing_type=sa.String(300),
        nullable=True,
        server_default=None,
    )
    op.alter_column(
        "parcel_sale_history", "grantor",
        existing_type=sa.String(300),
        nullable=True,
        server_default=None,
    )
