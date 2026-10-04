import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool, text

from alembic import context

# Ensure ADAM root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from adam.config import get_database_url
from adam.db.models import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url():
    """Retrieve database URL from config, env, or application config."""
    cfg_url = config.get_main_option("sqlalchemy.url")
    if cfg_url and "driver://" not in cfg_url:
        return cfg_url
    return os.environ.get("DATABASE_URL") or get_database_url()


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def compare_type_filter(context, inspected_column, metadata_column, inspected_type, metadata_type):
    # In SQLite, pgvector VECTOR is reflected as NUMERIC, which is expected
    if context.connection.dialect.name == "sqlite":
        meta_str = str(metadata_type).upper()
        ins_str = str(inspected_type).upper()
        if "VECTOR" in meta_str and "NUMERIC" in ins_str:
            return False
    return None


def include_object(object, name, type_, reflected, compare_to):
    if type_ == "table" and name in ("schema_migrations", "spatial_ref_sys"):
        return False
    return True


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        if connection.dialect.name == "postgresql":
            try:
                connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
                connection.commit()
            except Exception:
                pass

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=compare_type_filter,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
