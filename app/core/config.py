"""Environment-driven application settings."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

AppEnvironment = Literal["local", "test", "development", "staging", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
LogFormat = Literal["json", "console"]
CorsOrigins = Annotated[list[str], NoDecode]

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

    @field_validator("service_name", "app_version", mode="before")
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


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings.

    Required fields are supplied by environment variables or .env at runtime.
    """
    return Settings()  # type: ignore[call-arg]
