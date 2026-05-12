"""Alembic env — usa as configs do app."""
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import sys, os

# adiciona projeto ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.config import get_settings
from app.models import metadata as target_metadata  # noqa: F401

config = context.config

# Sobrescreve a URL com a do .env
settings = get_settings()
db_url = settings.database_url
# Alembic é síncrono — converte de async se necessário
if "+asyncpg" in db_url:
    db_url = db_url.replace("+asyncpg", "+psycopg")
config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"),
                      target_metadata=target_metadata,
                      literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}),
                                     prefix="sqlalchemy.",
                                     poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
