"""Standard error response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ErrorDetail(BaseModel):
    """Machine-readable error body."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: list[dict[str, Any]] | None = Field(default=None)


class ErrorResponse(BaseModel):
    """Envelope used by all global exception handlers."""

    model_config = ConfigDict(extra="forbid")

    error: ErrorDetail
