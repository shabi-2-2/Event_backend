"""Framework-agnostic security failures."""

from __future__ import annotations


class SecurityError(Exception):
    """Base class for failures raised by security services."""


class AuthenticationFailed(SecurityError):
    """Authentication could not be established.

    The reason is a stable, non-sensitive code suitable for structured logs.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__("Authentication failed.")


class AuthorizationDenied(SecurityError):
    """An authenticated principal lacks permission for the requested operation."""

    def __init__(self, reason: str = "insufficient_permission") -> None:
        self.reason = reason
        super().__init__("Authorization denied.")
