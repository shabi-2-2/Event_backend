"""Secure ticket-token generation and deterministic hashing utilities."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

_TOKEN_BYTES = 32
_REFERENCE_BYTES = 24
_DERIVATION_CONTEXT = b"event-ticket-token:v1:"


def generate_ticket_token() -> str:
    """Return a fresh URL-safe raw ticket token.

    Callers must hand the raw value to the delivery layer only and persist the
    result of :func:`hash_ticket_token` instead.
    """
    return secrets.token_urlsafe(_TOKEN_BYTES)


def generate_ticket_reference() -> str:
    """Return a random public ticket reference stored in the database.

    This value is an identifier, not a credential. The QR credential is derived
    from it with :func:`derive_ticket_token` and is never persisted in raw form.
    """
    return secrets.token_urlsafe(_REFERENCE_BYTES)


def derive_ticket_token(ticket_reference: str, derivation_key: str) -> str:
    """Derive the raw QR credential from a stored reference and server key.

    Derivation is deterministic so a separate email worker can recreate the raw
    token in memory without reading it from durable storage.
    """
    if not isinstance(ticket_reference, str) or not ticket_reference:
        raise ValueError("ticket_reference must be a non-empty string")
    if not isinstance(derivation_key, str) or not derivation_key:
        raise ValueError("derivation_key must be a non-empty string")
    material = _DERIVATION_CONTEXT + ticket_reference.encode("utf-8")
    digest = hmac.new(derivation_key.encode("utf-8"), material, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def hash_ticket_token(token: str) -> str:
    """Return the deterministic SHA-256 hex digest of a raw token."""
    if not isinstance(token, str) or not token:
        raise ValueError("token must be a non-empty string")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_ticket_token(token: str, token_hash: str) -> bool:
    """Hash a presented token and compare it to a stored digest safely."""
    if not isinstance(token_hash, str) or not token_hash:
        return False
    try:
        candidate = hash_ticket_token(token)
    except ValueError:
        return False
    return hmac.compare_digest(candidate, token_hash.lower())
