"""Google Forms webhook endpoint."""

from __future__ import annotations

import contextlib
import json
import logging

from fastapi import APIRouter, Depends, Request, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.logging import get_logger, log_event
from app.db.session import get_session
from app.schemas.webhook import RsvpWebhookRequest, WebhookOutcomeCode, WebhookResponse
from app.security.rate_limit import RateLimitScope, build_subject, enforce_rate_limit
from app.security.webhook import WebhookIdentity, require_webhook_auth
from app.services import webhook_ingestion

logger = get_logger(__name__)
router = APIRouter(tags=["webhooks"])


def _decode_json(raw_body: bytes) -> object | None:
    try:
        decoded: object = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return decoded


def _apply_status(response: Response, outcome: WebhookOutcomeCode) -> None:
    if outcome == WebhookOutcomeCode.REGISTERED:
        response.status_code = 201
    elif outcome == WebhookOutcomeCode.REJECTED_VALIDATION:
        response.status_code = 422
    else:
        response.status_code = 200


def _to_response(
    response: Response, result: webhook_ingestion.WebhookProcessingResult
) -> WebhookResponse:
    _apply_status(response, result.outcome)
    return WebhookResponse(
        success=result.success,
        outcome=result.outcome,
        submission_id=result.submission_id,
        message=result.message,
    )


@router.post("/webhooks/google-forms", response_model=WebhookResponse)
async def google_forms_webhook(
    request: Request,
    response: Response,
    identity: WebhookIdentity = Depends(require_webhook_auth),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> WebhookResponse:
    """Authenticate, rate-limit, and ingest a signed RSVP submission."""
    enforce_rate_limit(
        request,
        RateLimitScope.WEBHOOK,
        build_subject("webhook", identity.key_id),
    )

    # require_webhook_auth has already read and cached these exact bytes.
    raw_body = await request.body()
    parsed = _decode_json(raw_body)
    payload: RsvpWebhookRequest | None = None
    if parsed is not None:
        with contextlib.suppress(ValidationError):
            payload = RsvpWebhookRequest.model_validate(parsed)

    if payload is None:
        result = webhook_ingestion.record_validation_rejection(session, raw_body, parsed)
    else:
        result = webhook_ingestion.process_rsvp(session, payload, raw_body)

    log_event(
        logger,
        logging.INFO,
        "webhook_processed",
        outcome=result.outcome.value,
        submission_id=result.submission_id,
    )
    return _to_response(response, result)
