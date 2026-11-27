"""Portable tests for ticket credential derivation, QR generation, and email safety."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import qrcode

from app.security.ticket_tokens import (
    derive_ticket_token,
    generate_ticket_reference,
    hash_ticket_token,
    verify_ticket_token,
)
from app.services.ticket_email import QR_CONTENT_ID, TicketEmailContext, render_ticket_email
from app.services.ticket_qr import generate_ticket_qr_png, qr_png_to_base64

KEY = "test-derivation-key-with-at-least-32-characters"


def _context() -> TicketEmailContext:
    return TicketEmailContext(
        attendee_name="<Ada & Grace>",
        event_name="Summer <Social>",
        event_description="A private < gathering >",
        starts_at=datetime(2026, 7, 1, 9, tzinfo=UTC),
        ends_at=datetime(2026, 7, 1, 18, tzinfo=UTC),
        timezone_name="UTC",
        venue="Main Hall",
        ticket_code="public-reference",
    )


def test_derived_token_is_stable_and_verifiable() -> None:
    reference = generate_ticket_reference()
    token = derive_ticket_token(reference, KEY)

    assert token != reference
    assert len(token) >= 40
    assert token == derive_ticket_token(reference, KEY)
    assert token != derive_ticket_token(reference, f"{KEY}-other")
    assert verify_ticket_token(token, hash_ticket_token(token)) is True


def test_qr_payload_is_only_the_raw_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = derive_ticket_token(generate_ticket_reference(), KEY)
    captured: list[object] = []
    original = qrcode.QRCode.add_data

    def spy(self: qrcode.QRCode, data: object, *args: object, **kwargs: object) -> None:
        captured.append(data)
        original(self, data, *args, **kwargs)

    monkeypatch.setattr(qrcode.QRCode, "add_data", spy)

    qr_png = generate_ticket_qr_png(token)

    assert captured == [token]
    assert qr_png.startswith(b"\x89PNG\r\n\x1a\n")
    assert qr_png_to_base64(qr_png).encode("ascii").startswith(b"iVBOR")


def test_ticket_email_has_event_details_but_no_raw_token() -> None:
    token = derive_ticket_token(generate_ticket_reference(), KEY)
    html_body, text_body = render_ticket_email(_context())

    assert "Summer &lt;Social&gt;" in html_body
    assert "&lt;Ada &amp; Grace&gt;" in html_body
    assert "Main Hall" in html_body
    assert f"cid:{QR_CONTENT_ID}" in html_body
    assert token not in html_body
    assert token not in text_body
    assert "A private < gathering >" not in html_body
