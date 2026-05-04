"""v0.14 — add parcel_sale_history table

Revision ID: g8h9i0j1k2l3
Revises: f7a8b9c0d1e2
Create Date: 2026-05-04
"""
from alembic import op
import sqlalchemy as sa

revision = "g8h9i0j1k2l3"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "parcel_sale_history",
        sa.Column("id",                 sa.Integer(),              primary_key=True, autoincrement=True),

        # Property identity
        sa.Column("county_fips",        sa.String(5),              nullable=False),
        sa.Column("parcel_id",          sa.String(30),             nullable=False),

        # Transaction
        sa.Column("sale_date",          sa.Date(),                 nullable=True),
        sa.Column("sale_price",         sa.Integer(),              nullable=True),
        sa.Column("instrument_type",    sa.String(10),             nullable=True),
        sa.Column("qualification_code", sa.String(5),              nullable=True),
        sa.Column("sale_type",          sa.String(5),              nullable=True),
        sa.Column("multi_parcel",       sa.Boolean(),              nullable=False,
                  server_default=sa.text("false")),

        # Parties
        sa.Column("grantor",            sa.String(300),            nullable=True),
        sa.Column("grantee",            sa.String(300),            nullable=True),

        # Derived
        sa.Column("price_per_sqft",     sa.Numeric(8, 2),          nullable=True),

        # Provenance
        sa.Column("source",             sa.String(100),            nullable=False),
        sa.Column("scraped_at",         sa.DateTime(timezone=True),
                  server_default=sa.text("now()"),                 nullable=False),

        # Constraints
        sa.UniqueConstraint(
            "county_fips", "parcel_id", "sale_date", "grantor", "grantee",
            name="uq_psh_county_parcel_sale",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_parcel_sale_history"),
    )

    op.create_index("ix_psh_county_parcel",      "parcel_sale_history", ["county_fips", "parcel_id"])
    op.create_index("ix_psh_sale_date",          "parcel_sale_history", ["sale_date"])
    op.create_index("ix_psh_qualification_code", "parcel_sale_history", ["qualification_code"])
    op.create_index("ix_psh_grantor",            "parcel_sale_history", ["grantor"])
    op.create_index("ix_psh_grantee",            "parcel_sale_history", ["grantee"])


def downgrade() -> None:
    op.drop_index("ix_psh_grantee",            table_name="parcel_sale_history")
    op.drop_index("ix_psh_grantor",            table_name="parcel_sale_history")
    op.drop_index("ix_psh_qualification_code", table_name="parcel_sale_history")
    op.drop_index("ix_psh_sale_date",          table_name="parcel_sale_history")
    op.drop_index("ix_psh_county_parcel",      table_name="parcel_sale_history")
    op.drop_table("parcel_sale_history")
