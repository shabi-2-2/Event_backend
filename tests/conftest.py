"""Shared pytest configuration."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

# Isolate tests from developer shell/.env values before importing the app module.
os.environ["EVENT_APP_ENV"] = "test"
os.environ["EVENT_DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ.setdefault("EVENT_LOG_LEVEL", "INFO")
os.environ.setdefault("EVENT_LOG_FORMAT", "json")
os.environ.pop("EVENT_CORS_ORIGINS", None)
os.environ.pop("EVENT_DOCS_ENABLED", None)

from app.core.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture
def settings() -> Settings:
    """Return test-safe settings with explicit CORS origins."""
    return Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+pysqlite:///:memory:",
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
