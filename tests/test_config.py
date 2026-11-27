"""Configuration validation tests."""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

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


def test_webhook_signing_keys_parse_as_secret_strings() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+pysqlite:///:memory:",
        webhook_signing_keys='{"v1":"first-secret","v2":"second-secret"}',
    )

    assert set(settings.webhook_signing_keys) == {"v1", "v2"}
    assert isinstance(settings.webhook_signing_keys["v1"], SecretStr)
    assert settings.webhook_signing_keys["v2"].get_secret_value() == "second-secret"
    assert "first-secret" not in repr(settings)


def test_webhook_signing_keys_reject_invalid_key_ids_and_empty_secrets() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="test",
            database_url="sqlite+pysqlite:///:memory:",
            webhook_signing_keys='{"bad id":"secret"}',
        )

    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="test",
            database_url="sqlite+pysqlite:///:memory:",
            webhook_signing_keys='{"v1":""}',
        )


def test_supabase_urls_derive_issuer_and_jwks_url() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+pysqlite:///:memory:",
        supabase_url="https://project.supabase.co/",
    )

    assert settings.jwt_issuer_value == "https://project.supabase.co/auth/v1"
    assert (
        settings.supabase_jwks_url_value
        == "https://project.supabase.co/auth/v1/.well-known/jwks.json"
    )
