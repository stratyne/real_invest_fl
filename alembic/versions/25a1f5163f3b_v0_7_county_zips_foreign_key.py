"""county_zips — add foreign key to counties

Revision ID: 25a1f5163f3b
Revises: 390bc7eab733
Create Date: 2026-04-26
"""
from alembic import op

revision = '25a1f5163f3b'
down_revision = '390bc7eab733'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_foreign_key(
        'fk_county_zips_county_fips',
        'county_zips',
        'counties',
        ['county_fips'],
        ['county_fips'],
        ondelete='CASCADE',
    )


def downgrade() -> None:
    op.drop_constraint(
        'fk_county_zips_county_fips',
        'county_zips',
        type_='foreignkey',
    )
