"""Event-scoped eligibility roster request and response contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RosterCsvRequest(BaseModel):
    """A CSV roster supplied as base64 so no temporary upload file is created."""

    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, max_length=255)
    content_base64: str = Field(min_length=1)


class RosterConfirmRequest(RosterCsvRequest):
    """Confirmed import requires an explicit, independently validated flag."""

    confirm: Literal[True]


class RosterEntryResponse(BaseModel):
    """A roster entry for authorized event administrators only."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    normalized_urn: str = Field(max_length=64)
    created_at: datetime


class RosterImportResponse(BaseModel):
    """Safe import counts. Never includes submitted URNs or row contents."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["dry_run", "confirmed"]
    rows: int
    valid_unique: int
    duplicates: int
    invalid_rows: int
    already_imported: int
    imported: int
    skipped: int
