"""Alembic environment configuration."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context

import app.db.models  # noqa: E402,F401  # register all mapped classes
import app.security.rate_limit  # noqa: E402,F401  # register rate-limit table
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import create_db_engine

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
# Escape percent signs for ConfigParser interpolation in credentials.
config.set_main_option("sqlalchemy.url", settings.database_url_value().replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Render migration SQL without connecting to the database."""
    context.configure(
        url=settings.database_url_value(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
    connectable = create_db_engine(settings)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
