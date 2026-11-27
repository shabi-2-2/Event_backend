"""Shared pytest configuration."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

# Isolate tests from developer shell/.env values before importing the app module.
# EVENT_DATABASE_URL is respected when explicitly supplied so PostgreSQL tests can
# point Alembic at an isolated test database.
os.environ["EVENT_APP_ENV"] = "test"
os.environ.setdefault("EVENT_DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("EVENT_LOG_LEVEL", "INFO")
os.environ.setdefault("EVENT_LOG_FORMAT", "json")
os.environ.pop("EVENT_CORS_ORIGINS", None)
os.environ.pop("EVENT_DOCS_ENABLED", None)

import app.db.models  # noqa: E402,F401  # register models on Base.metadata
from app.core.config import Settings, get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import create_db_engine, create_session_factory  # noqa: E402
from app.main import create_app  # noqa: E402

_SQLITE_URL = "sqlite+pysqlite:///:memory:"


@pytest.fixture
def settings() -> Settings:
    """Return test-safe settings with explicit CORS origins."""
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=_SQLITE_URL,
        cors_origins=["http://testserver"],
    )


@pytest.fixture
def app(settings: Settings):
    """Return a fresh application instance."""
    return create_app(settings)


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    """Return a started test client."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def sqlite_engine() -> Iterator[Engine]:
    """Return an in-memory SQLite engine with the full schema created."""
    engine = create_engine(_SQLITE_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(sqlite_engine: Engine) -> Iterator[Session]:
    """Return a database session backed by the in-memory SQLite engine."""
    factory = sessionmaker(bind=sqlite_engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session


@pytest.fixture(scope="session")
def postgres_url() -> str:
    """Return the explicitly configured isolated PostgreSQL test URL."""
    url = os.environ.get("EVENT_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("EVENT_TEST_POSTGRES_URL is not configured")
    if "test" not in url.lower():
        raise RuntimeError("EVENT_TEST_POSTGRES_URL must point to a test database")
    if os.environ.get("EVENT_DATABASE_URL") != url:
        raise RuntimeError(
            "EVENT_DATABASE_URL must match EVENT_TEST_POSTGRES_URL so Alembic "
            "verifies the same database"
        )
    return url


@pytest.fixture(scope="session")
def migrated_postgres(postgres_url: str) -> Iterator[Engine]:
    """Reset an isolated test schema and apply the Alembic migration chain."""
    reset_engine = create_engine(postgres_url)
    with reset_engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    reset_engine.dispose()

    get_settings.cache_clear()
    alembic_config = Config("alembic.ini")
    command.upgrade(alembic_config, "head")

    engine = create_engine(postgres_url)
    yield engine
    engine.dispose()


@pytest.fixture
def pg_session(migrated_postgres: Engine) -> Iterator[Session]:
    """Return a PostgreSQL session wrapped in a rolled-back transaction."""
    connection = migrated_postgres.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        autoflush=False,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def postgres_engine_settings(settings: Settings) -> Settings:
    """Return settings whose engine uses the isolated PostgreSQL database."""
    url = os.environ.get("EVENT_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("EVENT_TEST_POSTGRES_URL is not configured")
    return settings.model_copy(update={"database_url": url})


@pytest.fixture
def postgres_engine(postgres_engine_settings: Settings) -> Iterator[Engine]:
    """Return a SQLAlchemy engine for the isolated PostgreSQL database."""
    engine = create_db_engine(postgres_engine_settings)
    yield engine
    engine.dispose()


@pytest.fixture
def postgres_session_factory(postgres_engine: Engine) -> Iterator[sessionmaker[Session]]:
    """Return a session factory for the isolated PostgreSQL database."""
    yield create_session_factory(postgres_engine)
