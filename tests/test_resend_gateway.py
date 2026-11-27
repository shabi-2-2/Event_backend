"""Resend gateway tests with the external API fully mocked."""

from __future__ import annotations

from typing import Any

import pytest
import resend
from pydantic import SecretStr

from app.core.config import Settings
from app.services.email_gateway import EmailDeliveryError, ResendEmailGateway, TicketEmailPayload


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=SecretStr("sqlite+pysqlite:///:memory:"),
        resend_api_key=SecretStr("re_test_key"),
        resend_from_email="tickets@example.com",  # type: ignore[arg-type]
        resend_from_name="Event Team",
    )


def test_send_ticket_email_uses_resend_with_stable_idempotency_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeResponse:
        id = "msg_abc123"

    def fake_send(params: object, options: object) -> FakeResponse:
        captured["params"] = params
        captured["options"] = options
        return FakeResponse()

    monkeypatch.setattr(resend.Emails, "send", fake_send)
    gateway = ResendEmailGateway(_settings())
    payload = TicketEmailPayload(
        to_email="attendee@example.com",
        subject="Your ticket",
        html="<p>ticket</p>",
        text="ticket",
        qr_base64="aGVsbG8=",
        idempotency_key="ticket-email:00000000-0000-0000-0000-000000000001",
    )

    message_id = gateway.send_ticket_email(payload)

    assert message_id == "msg_abc123"
    assert resend.api_key == "re_test_key"
    assert captured["options"] == {
        "idempotency_key": "ticket-email:00000000-0000-0000-0000-000000000001"
    }
    params = captured["params"]
    assert params["from"] == "Event Team <tickets@example.com>"
    assert params["to"] == ["attendee@example.com"]
    assert params["attachments"][0]["filename"] == "ticket-qr.png"
    assert params["attachments"][0]["content_id"] == "ticket-qr.png"


def test_gateway_requires_configuration() -> None:
    settings = _settings().model_copy(update={"resend_api_key": None})

    with pytest.raises(EmailDeliveryError, match="resend_api_key_missing"):
        ResendEmailGateway(settings)
