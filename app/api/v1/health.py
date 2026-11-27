"""Versioned health and readiness endpoints."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Request, Response, status

from app.core.config import Settings
from app.db.session import get_db_health
from app.schemas.health import ApiHealthResponse, ReadinessResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=ApiHealthResponse)
async def api_health(request: Request) -> ApiHealthResponse:
    """Return service and API version information."""
    settings: Settings = request.app.state.settings
    return ApiHealthResponse(
        status="healthy",
        service=settings.service_name,
        api_version=settings.api_version,
        app_version=settings.app_version,
    )


@router.get("/ready", response_model=ReadinessResponse)
async def readiness(
    response: Response,
    database_ready: bool = Depends(get_db_health),
) -> ReadinessResponse:
    """Return readiness based on critical dependency connectivity."""
    database_status: Literal["ready", "unavailable"] = "ready" if database_ready else "unavailable"
    overall_status: Literal["ready", "not_ready"] = "ready" if database_ready else "not_ready"

    if not database_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(status=overall_status, checks={"database": database_status})
