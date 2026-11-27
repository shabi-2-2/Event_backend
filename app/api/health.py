"""Unversioned liveness endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.config import Settings
from app.schemas.health import RootHealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=RootHealthResponse)
async def root_health(request: Request) -> RootHealthResponse:
    """Return a minimal liveness response for platform probes."""
    settings: Settings = request.app.state.settings
    return RootHealthResponse(status="healthy", service=settings.service_name)
