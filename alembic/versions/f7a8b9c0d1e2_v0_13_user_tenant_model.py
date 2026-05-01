"""v0.13 — user/tenant model

Adds: users, user_county_access, subscription_bundles, bundle_counties.
Alters: filter_profiles (add user_id, replace global unique constraint
        with two partial unique indexes), outreach_log (add user_id).
Drops: ui_sessions (stub, zero rows, no FK references).

Revision ID: f7a8b9c0d1e2
Revises: e5f6a7b8c9d0
Create Date: 2026-05-01
"""
from alembic import op
import sqlalchemy as sa

revision = "f7a8b9c0d1e2"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:

    # ------------------------------------------------------------------ #
    # 1. users                                                             #
    # ------------------------------------------------------------------ #
    op.create_table(
        "users",
        sa.Column("id",              sa.Integer(),      primary_key=True, autoincrement=True),
        sa.Column("email",           sa.String(255),    nullable=False),
        sa.Column("hashed_password", sa.String(255),    nullable=False),
        sa.Column("full_name",       sa.String(200),    nullable=True),
        sa.Column("is_active",       sa.Boolean(),      nullable=False, server_default=sa.text("true")),
        sa.Column("is_superuser",    sa.Boolean(),      nullable=False, server_default=sa.text("false")),
        sa.Column("created_at",      sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at",      sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    # ------------------------------------------------------------------ #
    # 2. subscription_bundles                                              #
    # ------------------------------------------------------------------ #
    op.create_table(
        "subscription_bundles",
        sa.Column("id",          sa.Integer(),   primary_key=True, autoincrement=True),
        sa.Column("bundle_name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("is_active",   sa.Boolean(),   nullable=False, server_default=sa.text("true")),
        sa.Column("created_at",  sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_subscription_bundles"),
        sa.UniqueConstraint("bundle_name", name="uq_bundle_name"),
    )

    # ------------------------------------------------------------------ #
    # 3. bundle_counties                                                   #
    # ------------------------------------------------------------------ #
    op.create_table(
        "bundle_counties",
        sa.Column("bundle_id",   sa.Integer(),  nullable=False),
        sa.Column("county_fips", sa.String(5),  nullable=False),
        sa.ForeignKeyConstraint(
            ["bundle_id"], ["subscription_bundles.id"],
            ondelete="CASCADE", name="fk_bc_bundle_id"
        ),
        sa.ForeignKeyConstraint(
            ["county_fips"], ["counties.county_fips"],
            name="fk_bc_county_fips"
        ),
        sa.PrimaryKeyConstraint("bundle_id", "county_fips", name="pk_bundle_counties"),
    )

    # ------------------------------------------------------------------ #
    # 4. user_county_access                                                #
    # ------------------------------------------------------------------ #
    op.create_table(
        "user_county_access",
        sa.Column("id",                 sa.Integer(),             nullable=False, autoincrement=True),
        sa.Column("user_id",            sa.Integer(),             nullable=False),
        sa.Column("county_fips",        sa.String(5),             nullable=False),
        sa.Column("granted_at",         sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("granted_by_user_id", sa.Integer(),             nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            ondelete="CASCADE", name="fk_uca_user_id"
        ),
        sa.ForeignKeyConstraint(
            ["county_fips"], ["counties.county_fips"],
            name="fk_uca_county_fips"
        ),
        sa.ForeignKeyConstraint(
            ["granted_by_user_id"], ["users.id"],
            ondelete="SET NULL", name="fk_uca_granted_by"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_county_access"),
        sa.UniqueConstraint("user_id", "county_fips", name="uq_user_county"),
    )
    op.create_index("ix_uca_user_id", "user_county_access", ["user_id"])

    # ------------------------------------------------------------------ #
    # 5. filter_profiles — add user_id, replace uniqueness constraint     #
    # ------------------------------------------------------------------ #
    # Drop the global unique constraint on profile_name.
    # Verify exact name with:
    #   SELECT conname FROM pg_constraint
    #   WHERE conrelid = 'filter_profiles'::regclass AND contype = 'u';
    op.drop_constraint(
        "filter_profiles_profile_name_key", "filter_profiles", type_="unique"
    )

    op.add_column(
        "filter_profiles",
        sa.Column(
            "user_id", sa.Integer(), nullable=True
        ),
    )
    op.create_foreign_key(
        "fk_fp_user_id",
        "filter_profiles", "users",
        ["user_id"], ["id"],
        ondelete="SET NULL",
    )

    # Partial unique index: system profiles (user_id IS NULL)
    op.execute(
        "CREATE UNIQUE INDEX uq_fp_system_county_name "
        "ON filter_profiles (county_fips, profile_name) "
        "WHERE user_id IS NULL"
    )
    # Partial unique index: user profiles (user_id IS NOT NULL)
    op.execute(
        "CREATE UNIQUE INDEX uq_fp_user_county_name "
        "ON filter_profiles (user_id, county_fips, profile_name) "
        "WHERE user_id IS NOT NULL"
    )

    # ------------------------------------------------------------------ #
    # 6. outreach_log — add user_id                                        #
    # ------------------------------------------------------------------ #
    op.add_column(
        "outreach_log",
        sa.Column("user_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_ol_user_id",
        "outreach_log", "users",
        ["user_id"], ["id"],
        ondelete="SET NULL",
    )

    # ------------------------------------------------------------------ #
    # 7. Drop ui_sessions                                                  #
    # ------------------------------------------------------------------ #
    op.drop_table("ui_sessions")


def downgrade() -> None:

    # Reverse order of upgrade

    # Restore ui_sessions stub
    op.create_table(
        "ui_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # outreach_log — remove user_id
    op.drop_constraint("fk_ol_user_id", "outreach_log", type_="foreignkey")
    op.drop_column("outreach_log", "user_id")

    # filter_profiles — remove user_id and partial indexes, restore global unique
    op.execute("DROP INDEX IF EXISTS uq_fp_user_county_name")
    op.execute("DROP INDEX IF EXISTS uq_fp_system_county_name")
    op.drop_constraint("fk_fp_user_id", "filter_profiles", type_="foreignkey")
    op.drop_column("filter_profiles", "user_id")
    op.create_unique_constraint(
        "filter_profiles_profile_name_key", "filter_profiles", ["profile_name"]
    )

    # user_county_access
    op.drop_index("ix_uca_user_id", table_name="user_county_access")
    op.drop_table("user_county_access")

    # bundle_counties
    op.drop_table("bundle_counties")

    # subscription_bundles
    op.drop_table("subscription_bundles")

    # users
    op.drop_table("users")
