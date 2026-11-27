"""Portable webhook schema validation and normalization tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.webhook import AttendanceValue, RsvpWebhookRequest

_BASE = {
    "event_slug": "summer-event",
    "submission_id": "submission-1",
    "name": "  Ada Lovelace  ",
    "email": "  Ada@Example.COM  ",
    "phone": "  555-0100  ",
    "urn": "  student-1  ",
    "attendance": " YES ",
}


def test_request_normalizes_safe_fields() -> None:
    request = RsvpWebhookRequest.model_validate(_BASE)

    assert request.event_slug == "summer-event"
    assert request.submission_id == "submission-1"
    assert request.name == "Ada Lovelace"
    assert str(request.email) == "ada@example.com"
    assert request.phone == "555-0100"
    assert request.urn == "STUDENT-1"
    assert request.attendance == AttendanceValue.YES


def test_empty_phone_becomes_none() -> None:
    request = RsvpWebhookRequest.model_validate({**_BASE, "phone": "   "})

    assert request.phone is None


def test_unknown_attendance_value_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RsvpWebhookRequest.model_validate({**_BASE, "attendance": "maybe"})


@pytest.mark.parametrize("field", ["event_slug", "submission_id", "name", "email", "urn"])
def test_required_fields_reject_empty_values(field: str) -> None:
    with pytest.raises(ValidationError):
        RsvpWebhookRequest.model_validate({**_BASE, field: "   "})


def test_invalid_email_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RsvpWebhookRequest.model_validate({**_BASE, "email": "not-an-email"})


def test_extra_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        RsvpWebhookRequest.model_validate({**_BASE, "sheet_row": 12})
