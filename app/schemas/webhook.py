"""Google Forms webhook request and response contracts."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class AttendanceValue(StrEnum):
    YES = "yes"
    NO = "no"


class WebhookOutcomeCode(StrEnum):
    """Stable, API-facing outcomes used in webhook responses."""

    REGISTERED = "registered"
    DECLINED = "declined"
    DUPLICATE_SUBMISSION = "duplicate_submission"
    ALREADY_REGISTERED = "already_registered"
    REJECTED_VALIDATION = "rejected_validation"
    EVENT_UNAVAILABLE = "event_unavailable"
    CAPACITY_REACHED = "capacity_reached"
    IDENTITY_CONFLICT = "identity_conflict"


class RsvpWebhookRequest(BaseModel):
    """Normalized RSVP payload supplied by the Google Apps Script sender."""

    model_config = ConfigDict(extra="forbid")

    event_slug: str = Field(min_length=1, max_length=100)
    submission_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr = Field(max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    urn: str = Field(min_length=1, max_length=64)
    attendance: AttendanceValue

    @field_validator("event_slug", "submission_id", "name", "urn", "email", mode="before")
    @classmethod
    def _trim_required(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("phone", mode="before")
    @classmethod
    def _normalize_phone(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        trimmed = value.strip()
        return trimmed or None

    @field_validator("attendance", mode="before")
    @classmethod
    def _normalize_attendance(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: EmailStr) -> str:
        return str(value).lower()

    @field_validator("urn")
    @classmethod
    def _normalize_urn(cls, value: str) -> str:
        return value.upper()


class WebhookResponse(BaseModel):
    """Predictable webhook response; never contains attendee personal data."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    outcome: WebhookOutcomeCode
    submission_id: str = Field(max_length=128)
    message: str
