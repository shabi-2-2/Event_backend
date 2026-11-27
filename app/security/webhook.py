"""HMAC-SHA256 authentication for future Google Apps Script webhooks."""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Request

from app.core.config import Settings
from app.core.errors import AppError
from app.core.logging import get_logger, log_event
from app.security.exceptions import AuthenticationFailed

logger = get_logger(__name__)

WEBHOOK_METHOD = "POST"
WEBHOOK_PATH = "/api/v1/webhooks/google-forms"
_HEADER_KEY_ID = "x-webhook-key-id"
_HEADER_TIMESTAMP = "x-webhook-timestamp"
_HEADER_SIGNATURE = "x-webhook-signature"

_KEY_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_TIMESTAMP_PATTERN = re.compile(r"^\d{1,20}$")
_HEX_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_SIGNATURE_PREFIX = "sha256="


@dataclass(frozen=True)
class WebhookIdentity:
    """The rotated key identifier that authenticated the request."""

    key_id: str


class WebhookAuthenticator:
    """Verify signed webhook requests without exposing secret material."""

    def __init__(
        self,
        settings: Settings,
        *,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._settings = settings
        self._now = now

    def verify(
        self,
        *,
        key_id: str | None,
        timestamp: str | None,
        signature: str | None,
        body: bytes,
    ) -> WebhookIdentity:
        """Verify headers and raw body, raising AuthenticationFailed on any error."""
        if not key_id or not timestamp or not signature:
            raise AuthenticationFailed("missing_headers")

        normalized_key_id = key_id.strip()
        if not _KEY_ID_PATTERN.fullmatch(normalized_key_id):
            raise AuthenticationFailed("unknown_key_id")

        secret = self._settings.webhook_signing_keys.get(normalized_key_id)
        if secret is None or not secret.get_secret_value().strip():
            raise AuthenticationFailed("unknown_key_id")

        normalized_timestamp = timestamp.strip()
        if not _TIMESTAMP_PATTERN.fullmatch(normalized_timestamp):
            raise AuthenticationFailed("invalid_timestamp")

        timestamp_value = int(normalized_timestamp)
        skew = abs(self._now() - timestamp_value)
        if skew > self._settings.webhook_timestamp_tolerance_seconds:
            raise AuthenticationFailed("timestamp_out_of_window")

        supplied_signature = signature.strip().lower()
        if supplied_signature.startswith(_SIGNATURE_PREFIX):
            supplied_signature = supplied_signature[len(_SIGNATURE_PREFIX) :]
        if not _HEX_SHA256_PATTERN.fullmatch(supplied_signature):
            raise AuthenticationFailed("invalid_signature")

        signed_message = f"{normalized_timestamp}.{WEBHOOK_METHOD}.{WEBHOOK_PATH}.".encode() + body
        expected_signature = hmac.new(
            secret.get_secret_value().encode("utf-8"),
            signed_message,
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected_signature, supplied_signature):
            raise AuthenticationFailed("invalid_signature")

        return WebhookIdentity(key_id=normalized_key_id)


async def require_webhook_auth(request: Request) -> WebhookIdentity:
    """FastAPI dependency that authenticates a raw webhook request body."""
    settings: Settings = request.app.state.settings

    # Reading the body here caches it on the Request, so later JSON parsing uses
    # the exact bytes that were authenticated.
    body = await request.body()

    authenticator = WebhookAuthenticator(settings)
    try:
        return authenticator.verify(
            key_id=request.headers.get(_HEADER_KEY_ID),
            timestamp=request.headers.get(_HEADER_TIMESTAMP),
            signature=request.headers.get(_HEADER_SIGNATURE),
            body=body,
        )
    except AuthenticationFailed as exc:
        log_event(logger, logging.WARNING, "webhook_auth_failed", reason=exc.reason)
        raise AppError(
            status_code=401,
            code="UNAUTHORIZED",
            message="Invalid webhook authentication.",
        ) from None
