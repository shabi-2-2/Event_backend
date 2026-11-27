"""Secure ticket-token generation and deterministic hashing utilities."""

from __future__ import annotations

import hashlib
import hmac
import secrets

_TOKEN_BYTES = 32


def generate_ticket_token() -> str:
    """Return a fresh URL-safe raw ticket token.

    Callers must hand the raw value to the delivery layer only and persist the
    result of :func:`hash_ticket_token` instead.
    """
    return secrets.token_urlsafe(_TOKEN_BYTES)


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
