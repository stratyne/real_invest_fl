"""
Alembic environment — reads SYNC_DATABASE_URL from .env for migrations.
Uses synchronous psycopg2 driver (required by Alembic).
Async engine (asyncpg) is used only by the FastAPI app at runtime.
"""
import os
from logging.config import fileConfig
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool
from alembic import context

# Load .env from project root — must happen before any model imports
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Import Base and all models so Alembic can see the full metadata
from real_invest_fl.db.base import Base  # noqa: E402
import real_invest_fl.db.models  # noqa: E402, F401

config = context.config

# Inject the real database URL from environment — overrides the dummy in alembic.ini
sync_url = os.environ.get("SYNC_DATABASE_URL")
if not sync_url:
    raise RuntimeError("SYNC_DATABASE_URL is not set in .env")
config.set_main_option("sqlalchemy.url", sync_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# PostGIS system tables that Alembic must never touch
POSTGIS_TABLES = {
    "spatial_ref_sys",
    "geometry_columns",
    "geography_columns",
    "raster_columns",
    "raster_overviews",
    "geocode_settings",
    "geocode_settings_default",
    "pagc_gaz",
    "pagc_lex",
    "pagc_rules",
    "topology",
    "layer",
    "tiger",
    "tiger_data",
}


def include_object(object, name, type_, reflected, compare_to):
    """Exclude PostGIS system tables and schemas from Alembic migrations."""
    if type_ == "table" and name in POSTGIS_TABLES:
        return False
    if type_ == "table" and reflected and compare_to is None:
        # Skip any reflected table that has no corresponding model
        # This catches any other PostGIS/system tables not in the list above
        return False
    return True


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
