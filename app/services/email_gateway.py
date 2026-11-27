"""Resend-backed email gateway used only by the separate worker process."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

import resend

from app.core.config import Settings
from app.services.ticket_email import QR_CONTENT_ID, QR_FILENAME

_UNSAFE_CODE_CHARS = re.compile(r"[^a-z0-9_]+")


class EmailDeliveryError(Exception):
    """A provider failure with a safe, non-PII error code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class TicketEmailPayload:
    """Everything needed to make one idempotent Resend request."""

    to_email: str
    subject: str
    html: str
    text: str
    qr_base64: str
    idempotency_key: str


class TicketEmailSender(Protocol):
    """Minimal send interface used by the worker and its tests."""

    def send_ticket_email(self, payload: TicketEmailPayload) -> str: ...


def _safe_error_code(exc: Exception) -> str:
    raw = type(exc).__name__.lower()
    code = _UNSAFE_CODE_CHARS.sub("_", raw).strip("_") or "provider_error"
    return f"resend_{code}"[:64]


class ResendEmailGateway:
    """Send ticket emails through Resend with a stable idempotency key."""

    def __init__(self, settings: Settings) -> None:
        api_key = settings.resend_api_key_value()
        from_email = settings.resend_from_email_value()
        if not api_key:
            raise EmailDeliveryError("resend_api_key_missing")
        if not from_email:
            raise EmailDeliveryError("resend_from_email_missing")
        self._api_key = api_key
        self._from_email = from_email
        self._from_name = settings.resend_from_name

    def send_ticket_email(self, payload: TicketEmailPayload) -> str:
        """Return the provider message ID, never echoing recipient details."""
        resend.api_key = self._api_key
        params: dict[str, Any] = {
            "from": f"{self._from_name} <{self._from_email}>",
            "to": [payload.to_email],
            "subject": payload.subject,
            "html": payload.html,
            "text": payload.text,
            "attachments": [
                {
                    "content": payload.qr_base64,
                    "filename": QR_FILENAME,
                    "content_type": "image/png",
                    "content_id": QR_CONTENT_ID,
                }
            ],
            "tags": [{"name": "purpose", "value": "ticket_issued"}],
        }
        options: dict[str, Any] = {"idempotency_key": payload.idempotency_key}
        try:
            response = resend.Emails.send(params, options)  # type: ignore[arg-type]
        except Exception as exc:
            raise EmailDeliveryError(_safe_error_code(exc)) from exc
        message_id = getattr(response, "id", None)
        if not isinstance(message_id, str) or not message_id:
            raise EmailDeliveryError("resend_missing_message_id")
        return message_id
