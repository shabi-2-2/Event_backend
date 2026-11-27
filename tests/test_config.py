"""Configuration validation tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_require_app_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EVENT_APP_ENV", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_reject_invalid_app_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVENT_APP_ENV", "qa")
    monkeypatch.setenv("EVENT_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_reject_unsupported_database_url() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="test",
            database_url="mysql://user:password@localhost/events",
        )


def test_settings_parse_comma_separated_cors_origins() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+pysqlite:///:memory:",
        cors_origins="https://admin.example.com, https://scanner.example.com",
    )
    assert settings.cors_origins == [
        "https://admin.example.com",
        "https://scanner.example.com",
    ]


def test_settings_expose_versioned_api_prefix() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+pysqlite:///:memory:",
    )
    assert settings.api_prefix == "/api/v1"
