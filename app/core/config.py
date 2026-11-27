"""Environment-driven application settings."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Annotated, Any, Literal

from pydantic import EmailStr, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

AppEnvironment = Literal["local", "test", "development", "staging", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
LogFormat = Literal["json", "console"]
CorsOrigins = Annotated[list[str], NoDecode]
SupabaseJwtStrategy = Literal["hs256", "jwks"]

_KEY_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_URL_SCHEME_PATTERN = re.compile(r"^https?://", re.IGNORECASE)

_ALLOWED_DATABASE_SCHEMES = (
    "postgresql+psycopg://",
    "sqlite+pysqlite://",
)


class Settings(BaseSettings):
    """Validated settings loaded from environment variables and .env files."""

    model_config = SettingsConfigDict(
        env_prefix="EVENT_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: AppEnvironment
    service_name: str = Field(default="event-management-api", min_length=1)
    app_version: str = Field(default="0.1.0", min_length=1)
    api_version: Literal["v1"] = "v1"
    docs_enabled: bool = True

    log_level: LogLevel = "INFO"
    log_format: LogFormat = "json"

    cors_origins: CorsOrigins = Field(default_factory=list)

    database_url: SecretStr
    db_pool_size: int = Field(default=5, ge=1, le=100)
    db_max_overflow: int = Field(default=10, ge=0, le=100)
    db_pool_timeout_seconds: int = Field(default=30, ge=1, le=300)
    db_pool_recycle_seconds: int = Field(default=1800, ge=0)
    db_statement_timeout_ms: int = Field(default=30_000, ge=1_000)
    db_prepare_threshold: int | None = Field(default=0, ge=0)
    db_echo: bool = False

    # Webhook HMAC authentication. Values are JSON-encoded SecretStr mappings.
    webhook_signing_keys: dict[str, SecretStr] = Field(default_factory=dict)
    webhook_timestamp_tolerance_seconds: int = Field(default=300, ge=1, le=3600)

    # Supabase JWT verification.
    supabase_url: str | None = None
    supabase_jwt_strategy: SupabaseJwtStrategy = "hs256"
    supabase_jwt_secret: SecretStr | None = None
    supabase_jwks_url: str | None = None
    jwt_issuer: str | None = None
    jwt_audience: str = Field(default="authenticated", min_length=1)
    jwt_leeway_seconds: int = Field(default=0, ge=0)

    # Shared rate limiting. No Redis is required; the counters live in PostgreSQL.
    rate_limit_window_seconds: int = Field(default=60, ge=1)
    webhook_rate_limit: int = Field(default=60, ge=1)
    checkin_verify_rate_limit: int = Field(default=120, ge=1)
    checkin_confirm_rate_limit: int = Field(default=60, ge=1)
    admin_export_rate_limit: int = Field(default=10, ge=1)
    admin_roster_import_rate_limit: int = Field(default=5, ge=1)

    # Event-scoped eligibility roster imports. Defaults accept the inspected
    # 130-row CSV well within conservative operational limits.
    roster_import_max_upload_bytes: int = Field(default=1_048_576, ge=1024, le=10_485_760)
    roster_import_max_rows: int = Field(default=1_000, ge=1, le=10_000)

    # Ticket credentials are derived in memory from a stored public reference and
    # this server-side key. The default is local-only and rejected in production.
    ticket_token_derivation_key: SecretStr = Field(
        default=SecretStr("local-only-insecure-ticket-token-key-change-me")
    )

    # Resend and the ticket-email worker. The worker validates these at startup.
    resend_api_key: SecretStr | None = None
    resend_from_email: EmailStr | None = None
    resend_from_name: str = Field(default="Event Management", min_length=1, max_length=100)
    email_worker_poll_interval_seconds: float = Field(default=5.0, gt=0, le=300)
    email_worker_batch_size: int = Field(default=10, ge=1, le=200)
    email_worker_max_attempts: int = Field(default=5, ge=1, le=20)
    email_worker_lease_seconds: int = Field(default=60, ge=10, le=3600)
    email_retry_backoff_initial_seconds: float = Field(default=30.0, gt=0)
    email_retry_backoff_multiplier: float = Field(default=2.0, ge=1.0)
    email_retry_backoff_max_seconds: float = Field(default=3600.0, gt=0)

    @field_validator("service_name", "app_version", "resend_from_name", mode="before")
    @classmethod
    def _strip_non_empty(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                raise ValueError("value must not be empty")
            return stripped
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        if isinstance(value, (list, tuple, set)):
            return [str(origin).strip() for origin in value if str(origin).strip()]
        raise ValueError("cors origins must be a comma-separated string or a list")

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value().strip()
        if not raw.startswith(_ALLOWED_DATABASE_SCHEMES):
            allowed = ", ".join(_ALLOWED_DATABASE_SCHEMES)
            raise ValueError(f"database_url must use one of: {allowed}")
        return SecretStr(raw)

    @field_validator("webhook_signing_keys", mode="before")
    @classmethod
    def _parse_webhook_signing_keys(cls, value: object) -> object:
        if value is None:
            return {}
        if isinstance(value, str):
            if not value.strip():
                return {}
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError as exc:
                raise ValueError("webhook_signing_keys must be valid JSON") from exc
            if not isinstance(parsed, dict):
                raise ValueError("webhook_signing_keys must be a JSON object")
            return parsed
        return value

    @field_validator("webhook_signing_keys")
    @classmethod
    def _validate_webhook_signing_keys(cls, value: dict[str, SecretStr]) -> dict[str, SecretStr]:
        cleaned: dict[str, SecretStr] = {}
        for key_id, secret in value.items():
            normalized_id = key_id.strip()
            if not _KEY_ID_PATTERN.fullmatch(normalized_id):
                raise ValueError("webhook key IDs must match [A-Za-z0-9_-]{1,64}")
            raw = secret.get_secret_value().strip()
            if not raw:
                raise ValueError(f"webhook signing key '{normalized_id}' must not be empty")
            cleaned[normalized_id] = SecretStr(raw)
        return cleaned

    @field_validator("ticket_token_derivation_key")
    @classmethod
    def _validate_ticket_token_derivation_key(cls, value: SecretStr, info: Any) -> SecretStr:
        raw = value.get_secret_value().strip()
        if len(raw) < 32:
            raise ValueError("ticket_token_derivation_key must be at least 32 characters")
        if (
            raw == "local-only-insecure-ticket-token-key-change-me"
            and info.data.get("app_env") == "production"
        ):
            raise ValueError("ticket_token_derivation_key must be overridden in production")
        return SecretStr(raw)

    @model_validator(mode="after")
    def _validate_backoff(self) -> Settings:
        if self.email_retry_backoff_max_seconds < self.email_retry_backoff_initial_seconds:
            raise ValueError(
                "email_retry_backoff_max_seconds must be >= email_retry_backoff_initial_seconds"
            )
        return self

    @field_validator("supabase_url", "supabase_jwks_url", mode="before")
    @classmethod
    def _normalize_optional_url(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped.rstrip("/") or None
        return value

    @field_validator("supabase_url", "supabase_jwks_url")
    @classmethod
    def _validate_optional_url(cls, value: str | None) -> str | None:
        if value is not None and not _URL_SCHEME_PATTERN.match(value):
            raise ValueError("URL must start with http:// or https://")
        return value

    @property
    def api_prefix(self) -> str:
        """Versioned API prefix, e.g. /api/v1."""
        return f"/api/{self.api_version}"

    @property
    def is_production(self) -> bool:
        """Whether the app is running in production."""
        return self.app_env == "production"

    def database_url_value(self) -> str:
        """Return the raw database URL without exposing it via repr or logs."""
        return self.database_url.get_secret_value()

    def ticket_token_derivation_key_value(self) -> str:
        """Return the server-side key used to derive QR credentials in memory."""
        return self.ticket_token_derivation_key.get_secret_value()

    def resend_api_key_value(self) -> str | None:
        """Return the Resend API key only for the worker client constructor."""
        return self.resend_api_key.get_secret_value() if self.resend_api_key else None

    def resend_from_email_value(self) -> str | None:
        """Return the configured sender address as a plain string."""
        return str(self.resend_from_email) if self.resend_from_email else None

    @property
    def jwt_issuer_value(self) -> str | None:
        """Resolve the explicit issuer or the Supabase default issuer."""
        if self.jwt_issuer:
            return self.jwt_issuer.rstrip("/")
        if self.supabase_url:
            return f"{self.supabase_url}/auth/v1"
        return None

    @property
    def supabase_jwks_url_value(self) -> str | None:
        """Resolve the explicit JWKS URL or the Supabase default JWKS URL."""
        if self.supabase_jwks_url:
            return self.supabase_jwks_url
        if self.supabase_url:
            return f"{self.supabase_url}/auth/v1/.well-known/jwks.json"
        return None


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings.

    Required fields are supplied by environment variables or .env at runtime.
    """
    return Settings()  # type: ignore[call-arg]
