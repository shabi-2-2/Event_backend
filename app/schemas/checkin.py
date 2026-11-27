"""Scanner request and whitelisted response contracts."""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models.common import RegistrationStatus, TicketStatus

_STATION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._:-]{0,99}$")


class CheckinOutcome(StrEnum):
    VALID_TICKET = "valid_ticket"
    CHECKED_IN = "checked_in"
    ALREADY_CHECKED_IN = "already_checked_in"
    INVALID_TICKET = "invalid_ticket"
    REVOKED_TICKET = "revoked_ticket"
    EXPIRED_TICKET = "expired_ticket"
    REGISTRATION_CANCELLED = "registration_cancelled"
    INVALID_REGISTRATION_STATE = "invalid_registration_state"


class CheckinStatus(StrEnum):
    PENDING = "pending"
    CHECKED_IN = "checked_in"


class TicketCheckRequest(BaseModel):
    """Raw ticket token submitted by an authorized scanner."""

    model_config = ConfigDict(extra="forbid")

    ticket_token: str = Field(min_length=20, max_length=256)

    @field_validator("ticket_token", mode="before")
    @classmethod
    def _strip_token(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class ConfirmCheckinRequest(TicketCheckRequest):
    """Check-in confirmation request with an optional scanner station."""

    station: str | None = Field(default=None, max_length=100)

    @field_validator("station", mode="before")
    @classmethod
    def _normalize_station(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        return stripped or None

    @field_validator("station")
    @classmethod
    def _validate_station(cls, value: str | None) -> str | None:
        if value is not None and not _STATION_PATTERN.fullmatch(value):
            raise ValueError("station must be 1-100 safe characters")
        return value


class ScannerTicketInfo(BaseModel):
    """Only the fields a scanner is allowed to display."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    attendee_name: str
    urn: str
    ticket_status: TicketStatus
    registration_status: RegistrationStatus
    check_in_status: CheckinStatus


class CheckinResponse(BaseModel):
    """Predictable scanner response with no PII beyond whitelisted display data."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    success: bool
    outcome: CheckinOutcome
    message: str
    ticket: ScannerTicketInfo | None = None
