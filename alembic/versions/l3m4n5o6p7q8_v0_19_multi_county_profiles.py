"""v0.19 — Multi-county filter profiles

Converts filter_profiles.county_fips from a scalar VARCHAR(5) to a
VARCHAR(5)[] array, enabling a single filter profile to span multiple
counties. Existing single-county profiles are backfilled automatically.

Uniqueness model changes:
  System profiles: UNIQUE (profile_name) WHERE user_id IS NULL
  User profiles:   UNIQUE (user_id, profile_name) WHERE user_id IS NOT NULL
  county_fips removed from both unique constraints — array columns cannot
  participate in PostgreSQL unique indexes directly.

GIN index added on county_fips array for query-time containment checks.

Revision ID: l3m4n5o6p7q8
Revises: k2l3m4n5o6p7
Create Date: 2026-05-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

revision = 'l3m4n5o6p7q8'
down_revision = 'k2l3m4n5o6p7'
branch_labels = None
depends_on = None


def upgrade() -> None:

    # ------------------------------------------------------------------ #
    # 1. Drop existing partial unique indexes that include county_fips     #
    # ------------------------------------------------------------------ #
    op.drop_index("uq_fp_system_county_name", table_name="filter_profiles")
    op.drop_index("uq_fp_user_county_name", table_name="filter_profiles")

    # ------------------------------------------------------------------ #
    # 2. Add array column alongside scalar — nullable until backfilled     #
    # ------------------------------------------------------------------ #
    op.add_column(
        "filter_profiles",
        sa.Column(
            "county_fips_array",
            ARRAY(sa.String(5)),
            nullable=True,
        ),
    )

    # ------------------------------------------------------------------ #
    # 3. Backfill — wrap existing scalar into single-element array         #
    # ------------------------------------------------------------------ #
    op.execute(
        sa.text(
            "UPDATE filter_profiles SET county_fips_array = ARRAY[county_fips]"
        )
    )

    # ------------------------------------------------------------------ #
    # 4. Set NOT NULL now that every row is populated                      #
    # ------------------------------------------------------------------ #
    op.alter_column(
        "filter_profiles",
        "county_fips_array",
        nullable=False,
    )

    # ------------------------------------------------------------------ #
    # 5. Drop scalar county_fips column                                    #
    # ------------------------------------------------------------------ #
    op.drop_column("filter_profiles", "county_fips")

    # ------------------------------------------------------------------ #
    # 6. Rename array column to county_fips                                #
    # ------------------------------------------------------------------ #
    op.alter_column(
        "filter_profiles",
        "county_fips_array",
        new_column_name="county_fips",
    )

    # ------------------------------------------------------------------ #
    # 7. Rebuild partial unique indexes without county_fips                #
    # ------------------------------------------------------------------ #
    op.create_index(
        "uq_fp_system_name",
        "filter_profiles",
        ["profile_name"],
        unique=True,
        postgresql_where=sa.text("user_id IS NULL"),
    )
    op.create_index(
        "uq_fp_user_name",
        "filter_profiles",
        ["user_id", "profile_name"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )

    # ------------------------------------------------------------------ #
    # 8. GIN index for array containment queries                           #
    # ------------------------------------------------------------------ #
    op.create_index(
        "ix_fp_county_fips_gin",
        "filter_profiles",
        ["county_fips"],
        postgresql_using="gin",
    )


def downgrade() -> None:

    # ------------------------------------------------------------------ #
    # Reverse — collapse array back to scalar using first element          #
    # NOTE: profiles with multiple counties lose all but the first.        #
    # ------------------------------------------------------------------ #

    op.drop_index("ix_fp_county_fips_gin", table_name="filter_profiles")
    op.drop_index("uq_fp_user_name", table_name="filter_profiles")
    op.drop_index("uq_fp_system_name", table_name="filter_profiles")

    # Add scalar column alongside array
    op.add_column(
        "filter_profiles",
        sa.Column(
            "county_fips_scalar",
            sa.String(5),
            nullable=True,
        ),
    )

    # Backfill scalar from first array element
    op.execute(
        sa.text(
            "UPDATE filter_profiles SET county_fips_scalar = county_fips[1]"
        )
    )

    op.alter_column(
        "filter_profiles",
        "county_fips_scalar",
        nullable=False,
    )

    op.drop_column("filter_profiles", "county_fips")

    op.alter_column(
        "filter_profiles",
        "county_fips_scalar",
        new_column_name="county_fips",
    )

    # Rebuild original partial unique indexes
    op.create_index(
        "uq_fp_system_county_name",
        "filter_profiles",
        ["county_fips", "profile_name"],
        unique=True,
        postgresql_where=sa.text("user_id IS NULL"),
    )
    op.create_index(
        "uq_fp_user_county_name",
        "filter_profiles",
        ["user_id", "county_fips", "profile_name"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
