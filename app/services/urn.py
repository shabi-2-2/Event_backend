"""Shared URN normalization for roster imports and submitted RSVPs."""

from __future__ import annotations

URN_MAX_LENGTH = 64


class InvalidUrn(ValueError):
    """Raised when a URN cannot be normalized safely."""


def normalize_urn(value: object) -> str:
    """Trim and uppercase a URN without changing its meaningful characters.

    Leading zeros and punctuation are preserved. This is deliberately the same
    normalization used by the webhook request schema, so exact event-scoped
    matching cannot be bypassed by casing or surrounding whitespace.
    """

    if not isinstance(value, str):
        raise InvalidUrn("URN must be a string.")
    normalized = value.strip().upper()
    if not normalized:
        raise InvalidUrn("URN is required.")
    if len(normalized) > URN_MAX_LENGTH:
        raise InvalidUrn("URN is too long.")
    if any(ord(char) < 32 or ord(char) == 127 for char in normalized):
        raise InvalidUrn("URN contains unsupported control characters.")
    return normalized


def try_normalize_urn(value: object) -> str | None:
    """Return a normalized URN, or None for any invalid value."""

    try:
        return normalize_urn(value)
    except InvalidUrn:
        return None
