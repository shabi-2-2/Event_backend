"""Health and readiness response schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RootHealthResponse(BaseModel):
    """Minimal liveness response expected by uptime probes."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["healthy"]
    service: str


class ApiHealthResponse(BaseModel):
    """Versioned liveness response."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["healthy"]
    service: str
    api_version: str
    app_version: str


class ReadinessResponse(BaseModel):
    """Dependency readiness response."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ready", "not_ready"]
    checks: dict[str, Literal["ready", "unavailable"]] = Field(default_factory=dict)
