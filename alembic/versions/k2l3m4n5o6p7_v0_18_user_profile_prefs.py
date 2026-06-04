"""v0.18 - user_profile_prefs

Adds the user_profile_prefs table, which tracks per-user activity
and preference state for each filter_profile they have run or
favorited. Used by the dashboard and profile-search routes.

Revision ID: k2l3m4n5o6p7
Revises: j1k2l3m4n5o6
Create Date: 2026-05-14
"""
from alembic import op
import sqlalchemy as sa

revision = 'k2l3m4n5o6p7'
down_revision = 'j1k2l3m4n5o6'
branch_labels = None
depends_on = None


def upgrade() -> None:

    # ------------------------------------------------------------------ #
    # user_profile_prefs (new table)                                       #
    # ------------------------------------------------------------------ #
    op.create_table(
        "user_profile_prefs",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("is_favorite", sa.Boolean(), nullable=False,
                  server_default="false"),
        sa.Column("last_searched_at", sa.TIMESTAMP(timezone=True),
                  nullable=True),
        sa.Column("last_result_count", sa.Integer(), nullable=True),
        sa.Column("run_count", sa.Integer(), nullable=False,
                  server_default="0"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="user_profile_prefs_pkey"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_upp_user_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["filter_profiles.id"],
            name="fk_upp_profile_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("user_id", "profile_id",
                            name="uq_upp_user_profile"),
    )
    op.create_index(
        "ix_upp_user_favorite",
        "user_profile_prefs",
        ["user_id", "is_favorite"],
    )
    op.create_index(
        "ix_upp_user_last_searched",
        "user_profile_prefs",
        ["user_id", sa.text("last_searched_at DESC")],
    )


def downgrade() -> None:

    # ------------------------------------------------------------------ #
    # user_profile_prefs                                                   #
    # ------------------------------------------------------------------ #
    op.drop_index("ix_upp_user_last_searched",
                  table_name="user_profile_prefs")
    op.drop_index("ix_upp_user_favorite",
                  table_name="user_profile_prefs")
    op.drop_table("user_profile_prefs")
