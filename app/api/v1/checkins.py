"""QR ticket verification and atomic check-in endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.logging import get_logger, log_event
from app.db.session import get_session
from app.schemas.checkin import (
    CheckinResponse,
    ConfirmCheckinRequest,
    TicketCheckRequest,
)
from app.security.rate_limit import RateLimitScope, build_subject, enforce_rate_limit
from app.security.rbac import EventAccess, Permission, require_permission_by_slug
from app.services import checkin as checkin_service

logger = get_logger(__name__)
router = APIRouter(tags=["checkins"])


@router.post("/events/{event_slug}/checkins/verify", response_model=CheckinResponse)
async def verify_ticket(
    request: Request,
    payload: TicketCheckRequest,
    access: EventAccess = Depends(require_permission_by_slug(Permission.TICKET_VERIFY)),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> CheckinResponse:
    """Read-only verification of a scanned QR ticket."""

    enforce_rate_limit(
        request,
        RateLimitScope.CHECKIN_VERIFY,
        build_subject("checkin_verify", access.event_id, access.user_id),
    )
    result = checkin_service.verify_ticket(
        session,
        event_id=access.event_id,
        ticket_token=payload.ticket_token,
    )
    log_event(
        logger,
        logging.INFO,
        "checkin_verify_completed",
        event_id=str(access.event_id),
        actor_user_id=str(access.user_id),
        outcome=result.outcome.value,
    )
    return result


@router.post("/events/{event_slug}/checkins/confirm", response_model=CheckinResponse)
async def confirm_checkin(
    request: Request,
    payload: ConfirmCheckinRequest,
    access: EventAccess = Depends(require_permission_by_slug(Permission.TICKET_CHECKIN)),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> CheckinResponse:
    """Atomically confirm a scanned QR ticket without leaking credentials."""

    enforce_rate_limit(
        request,
        RateLimitScope.CHECKIN_CONFIRM,
        build_subject("checkin_confirm", access.event_id, access.user_id),
    )
    result = checkin_service.confirm_checkin(
        session,
        event_id=access.event_id,
        ticket_token=payload.ticket_token,
        station=payload.station,
        user_id=access.user_id,
    )
    log_event(
        logger,
        logging.INFO,
        "checkin_confirm_completed",
        event_id=str(access.event_id),
        actor_user_id=str(access.user_id),
        outcome=result.outcome.value,
    )
    return result
