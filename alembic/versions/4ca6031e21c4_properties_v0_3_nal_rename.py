"""properties table v0.3 — rename to NAL field names, drop situs_state,
   add new columns from NAL audit

Revision ID: 4ca6031e21c4
Revises: 54c4159dbf59
Create Date: 2026-04-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '4ca6031e21c4'
down_revision = '54c4159dbf59'
branch_labels = None
depends_on = None


def upgrade() -> None:

    # ------------------------------------------------------------------ #
    # SECTION 1 — Drop indexes that reference columns being renamed       #
    # ------------------------------------------------------------------ #
    op.drop_index('ix_properties_dor_use_code',  table_name='properties')
    op.drop_index('ix_properties_zip_code',       table_name='properties')
    op.drop_index(op.f('ix_properties_parcel_id_normalized'), table_name='properties')
    op.drop_index('ix_properties_act_yr_blt',     table_name='properties')
    op.drop_index('ix_properties_const_class',    table_name='properties')

    # ------------------------------------------------------------------ #
    # SECTION 2 — Drop situs_state column                                 #
    # ------------------------------------------------------------------ #
    op.drop_column('properties', 'situs_state')

    # ------------------------------------------------------------------ #
    # SECTION 3 — Rename existing columns to NAL field names              #
    # ------------------------------------------------------------------ #
    op.alter_column('properties', 'dor_county_no',         new_column_name='co_no')
    op.alter_column('properties', 'assessment_year',       new_column_name='asmnt_yr')
    op.alter_column('properties', 'dor_use_code',          new_column_name='dor_uc')
    op.alter_column('properties', 'pa_use_code',           new_column_name='pa_uc')
    op.alter_column('properties', 'just_value',            new_column_name='jv')
    op.alter_column('properties', 'assessed_value',        new_column_name='av_nsd')
    op.alter_column('properties', 'taxable_value',         new_column_name='tv_nsd')
    op.alter_column('properties', 'construction_class',    new_column_name='const_class')
    op.alter_column('properties', 'effective_year_built',  new_column_name='eff_yr_blt')
    op.alter_column('properties', 'actual_year_built',     new_column_name='act_yr_blt')
    op.alter_column('properties', 'total_living_area',     new_column_name='tot_lvg_area')
    op.alter_column('properties', 'land_square_footage',   new_column_name='lnd_sqfoot')
    op.alter_column('properties', 'num_buildings',         new_column_name='no_buldng')
    op.alter_column('properties', 'num_residential_units', new_column_name='no_res_unts')
    op.alter_column('properties', 'owner_name',            new_column_name='own_name')
    op.alter_column('properties', 'owner_address_line1',   new_column_name='own_addr1')
    op.alter_column('properties', 'owner_address_line2',   new_column_name='own_addr2')
    op.alter_column('properties', 'owner_city',            new_column_name='own_city')
    op.alter_column('properties', 'owner_state',           new_column_name='own_state')
    op.alter_column('properties', 'owner_zip',             new_column_name='own_zipcd')
    op.alter_column('properties', 'situs_address',         new_column_name='phy_addr1')
    op.alter_column('properties', 'situs_city',            new_column_name='phy_city')
    op.alter_column('properties', 'zip_code',              new_column_name='phy_zipcd')
    op.alter_column('properties', 'parcel_id_normalized',  new_column_name='state_par_id')

    # ------------------------------------------------------------------ #
    # SECTION 4 — Add new columns                                         #
    # All nullable — no existing rows, no defaults required               #
    # ------------------------------------------------------------------ #

    # Columns confirmed missing from live schema — add rather than rename
    op.add_column('properties', sa.Column('imp_qual',      sa.Integer(),          nullable=True))
    op.add_column('properties', sa.Column('spec_feat_val', sa.Integer(),          nullable=True))

    # Value signals
    op.add_column('properties', sa.Column('av_sd',         sa.Integer(),          nullable=True))
    op.add_column('properties', sa.Column('tv_sd',         sa.Integer(),          nullable=True))
    op.add_column('properties', sa.Column('jv_hmstd',      sa.Integer(),          nullable=True))
    op.add_column('properties', sa.Column('lnd_val',       sa.Integer(),          nullable=True))
    op.add_column('properties', sa.Column('exmpt_01',      sa.Integer(),          nullable=True))

    # Embedded sale history — Sale 1
    op.add_column('properties', sa.Column('multi_par_sal1', sa.String(length=1),  nullable=True))
    op.add_column('properties', sa.Column('qual_cd1',        sa.String(length=2),  nullable=True))
    op.add_column('properties', sa.Column('vi_cd1',          sa.String(length=1),  nullable=True))
    op.add_column('properties', sa.Column('sale_prc1',       sa.Integer(),          nullable=True))
    op.add_column('properties', sa.Column('sale_yr1',        sa.Integer(),          nullable=True))
    op.add_column('properties', sa.Column('sale_mo1',        sa.Integer(),          nullable=True))
    op.add_column('properties', sa.Column('sal_chng_cd1',    sa.String(length=1),  nullable=True))

    # Embedded sale history — Sale 2
    op.add_column('properties', sa.Column('multi_par_sal2', sa.String(length=1),  nullable=True))
    op.add_column('properties', sa.Column('qual_cd2',        sa.String(length=2),  nullable=True))
    op.add_column('properties', sa.Column('vi_cd2',          sa.String(length=1),  nullable=True))
    op.add_column('properties', sa.Column('sale_prc2',       sa.Integer(),          nullable=True))
    op.add_column('properties', sa.Column('sale_yr2',        sa.Integer(),          nullable=True))
    op.add_column('properties', sa.Column('sale_mo2',        sa.Integer(),          nullable=True))
    op.add_column('properties', sa.Column('sal_chng_cd2',    sa.String(length=1),  nullable=True))

    # Owner signals
    op.add_column('properties', sa.Column('own_state_dom',   sa.String(length=2),  nullable=True))

    # Condition and disaster flags
    op.add_column('properties', sa.Column('distr_cd',        sa.Integer(),          nullable=True))
    op.add_column('properties', sa.Column('distr_yr',        sa.Integer(),          nullable=True))
    op.add_column('properties', sa.Column('nconst_val',      sa.Integer(),          nullable=True))
    op.add_column('properties', sa.Column('del_val',         sa.Integer(),          nullable=True))
    op.add_column('properties', sa.Column('par_splt',        sa.String(length=5),  nullable=True))
    op.add_column('properties', sa.Column('spass_cd',        sa.String(length=1),  nullable=True))

    # Geographic signals
    op.add_column('properties', sa.Column('mkt_ar',          sa.String(length=3),  nullable=True))
    op.add_column('properties', sa.Column('nbrhd_cd',        sa.String(length=10), nullable=True))
    op.add_column('properties', sa.Column('census_bk',       sa.String(length=16), nullable=True))
    op.add_column('properties', sa.Column('twn',             sa.String(length=3),  nullable=True))
    op.add_column('properties', sa.Column('rng',             sa.String(length=3),  nullable=True))
    op.add_column('properties', sa.Column('sec',             sa.String(length=3),  nullable=True))

    # Data quality and longitudinal tracking
    # DT_LAST_INSPT: MMYY format — leading zeros meaningful, stored as String
    op.add_column('properties', sa.Column('dt_last_inspt',   sa.String(length=4),  nullable=True))
    op.add_column('properties', sa.Column('alt_key',         sa.String(length=26), nullable=True))
    op.add_column('properties', sa.Column('s_legal',         sa.String(length=30), nullable=True))

    # Derived / computed — populated during Stage 1 ingest
    op.add_column('properties', sa.Column('improvement_to_land_ratio',
                                          sa.Numeric(precision=8, scale=4),        nullable=True))
    op.add_column('properties', sa.Column('soh_compression_ratio',
                                          sa.Numeric(precision=6, scale=4),        nullable=True))
    op.add_column('properties', sa.Column('years_since_last_sale',
                                          sa.Integer(),                            nullable=True))

    # ------------------------------------------------------------------ #
    # SECTION 5 — Recreate renamed indexes and create new indexes         #
    # ------------------------------------------------------------------ #
    op.create_index('ix_properties_act_yr_blt',   'properties', ['act_yr_blt'],   unique=False)
    op.create_index('ix_properties_const_class',  'properties', ['const_class'],  unique=False)
    op.create_index('ix_properties_dor_uc',       'properties', ['dor_uc'],       unique=False)
    op.create_index('ix_properties_phy_zipcd',    'properties', ['phy_zipcd'],    unique=False)
    op.create_index('ix_properties_state_par_id', 'properties', ['state_par_id'], unique=False)
    op.create_index('ix_properties_jv',           'properties', ['jv'],           unique=False)
    op.create_index('ix_properties_sale_yr1',     'properties', ['sale_yr1'],     unique=False)
    op.create_index('ix_properties_mkt_ar',       'properties', ['mkt_ar'],       unique=False)
    op.create_index('ix_properties_census_bk',    'properties', ['census_bk'],    unique=False)


def downgrade() -> None:

    # Drop new indexes
    op.drop_index('ix_properties_census_bk',    table_name='properties')
    op.drop_index('ix_properties_mkt_ar',       table_name='properties')
    op.drop_index('ix_properties_sale_yr1',     table_name='properties')
    op.drop_index('ix_properties_jv',           table_name='properties')
    op.drop_index('ix_properties_state_par_id', table_name='properties')
    op.drop_index('ix_properties_phy_zipcd',    table_name='properties')
    op.drop_index('ix_properties_dor_uc',       table_name='properties')
    op.drop_index('ix_properties_const_class',  table_name='properties')
    op.drop_index('ix_properties_act_yr_blt',   table_name='properties')

    # Drop new columns
    op.drop_column('properties', 'years_since_last_sale')
    op.drop_column('properties', 'soh_compression_ratio')
    op.drop_column('properties', 'improvement_to_land_ratio')
    op.drop_column('properties', 's_legal')
    op.drop_column('properties', 'alt_key')
    op.drop_column('properties', 'dt_last_inspt')
    op.drop_column('properties', 'sec')
    op.drop_column('properties', 'rng')
    op.drop_column('properties', 'twn')
    op.drop_column('properties', 'census_bk')
    op.drop_column('properties', 'nbrhd_cd')
    op.drop_column('properties', 'mkt_ar')
    op.drop_column('properties', 'spass_cd')
    op.drop_column('properties', 'par_splt')
    op.drop_column('properties', 'del_val')
    op.drop_column('properties', 'nconst_val')
    op.drop_column('properties', 'distr_yr')
    op.drop_column('properties', 'distr_cd')
    op.drop_column('properties', 'own_state_dom')
    op.drop_column('properties', 'sal_chng_cd2')
    op.drop_column('properties', 'sale_mo2')
    op.drop_column('properties', 'sale_yr2')
    op.drop_column('properties', 'sale_prc2')
    op.drop_column('properties', 'vi_cd2')
    op.drop_column('properties', 'qual_cd2')
    op.drop_column('properties', 'multi_par_sal2')
    op.drop_column('properties', 'sal_chng_cd1')
    op.drop_column('properties', 'sale_mo1')
    op.drop_column('properties', 'sale_yr1')
    op.drop_column('properties', 'sale_prc1')
    op.drop_column('properties', 'vi_cd1')
    op.drop_column('properties', 'qual_cd1')
    op.drop_column('properties', 'multi_par_sal1')
    op.drop_column('properties', 'exmpt_01')
    op.drop_column('properties', 'lnd_val')
    op.drop_column('properties', 'jv_hmstd')
    op.drop_column('properties', 'tv_sd')
    op.drop_column('properties', 'av_sd')
    op.drop_column('properties', 'spec_feat_val')
    op.drop_column('properties', 'imp_qual')

    # Reverse renames
    op.alter_column('properties', 'state_par_id', new_column_name='parcel_id_normalized')
    op.alter_column('properties', 'phy_zipcd',    new_column_name='zip_code')
    op.alter_column('properties', 'phy_city',     new_column_name='situs_city')
    op.alter_column('properties', 'phy_addr1',    new_column_name='situs_address')
    op.alter_column('properties', 'own_zipcd',    new_column_name='owner_zip')
    op.alter_column('properties', 'own_state',    new_column_name='owner_state')
    op.alter_column('properties', 'own_city',     new_column_name='owner_city')
    op.alter_column('properties', 'own_addr2',    new_column_name='owner_address_line2')
    op.alter_column('properties', 'own_addr1',    new_column_name='owner_address_line1')
    op.alter_column('properties', 'own_name',     new_column_name='owner_name')
    op.alter_column('properties', 'no_res_unts',  new_column_name='num_residential_units')
    op.alter_column('properties', 'no_buldng',    new_column_name='num_buildings')
    op.alter_column('properties', 'lnd_sqfoot',   new_column_name='land_square_footage')
    op.alter_column('properties', 'tot_lvg_area', new_column_name='total_living_area')
    op.alter_column('properties', 'act_yr_blt',   new_column_name='actual_year_built')
    op.alter_column('properties', 'eff_yr_blt',   new_column_name='effective_year_built')
    op.alter_column('properties', 'const_class',  new_column_name='construction_class')
    op.alter_column('properties', 'tv_nsd',       new_column_name='taxable_value')
    op.alter_column('properties', 'av_nsd',       new_column_name='assessed_value')
    op.alter_column('properties', 'jv',           new_column_name='just_value')
    op.alter_column('properties', 'pa_uc',        new_column_name='pa_use_code')
    op.alter_column('properties', 'dor_uc',       new_column_name='dor_use_code')
    op.alter_column('properties', 'asmnt_yr',     new_column_name='assessment_year')
    op.alter_column('properties', 'co_no',        new_column_name='dor_county_no')

    # Restore situs_state
    op.add_column('properties', sa.Column('situs_state', sa.String(length=2), nullable=True))

    # Restore original indexes
    op.create_index('ix_properties_act_yr_blt',   'properties', ['actual_year_built'],    unique=False)
    op.create_index('ix_properties_const_class',  'properties', ['construction_class'],   unique=False)
    op.create_index('ix_properties_dor_use_code', 'properties', ['dor_use_code'],         unique=False)
    op.create_index('ix_properties_zip_code',     'properties', ['zip_code'],             unique=False)
    op.create_index(op.f('ix_properties_parcel_id_normalized'),
                    'properties', ['parcel_id_normalized'], unique=False)
