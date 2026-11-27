"""Supabase JWT verification with HS256 or rotating JWKS keys."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

import jwt
from fastapi import Request
from jwt import PyJWKClient

from app.core.config import Settings
from app.core.errors import AppError
from app.core.logging import get_logger, log_event
from app.security.exceptions import AuthenticationFailed

logger = get_logger(__name__)

_REQUIRED_CLAIMS = ["sub", "exp", "iat", "iss", "aud"]


class JWKClient(Protocol):
    """Minimal JWKS client contract used by the verifier."""

    def get_signing_key_from_jwt(self, token: str) -> Any:  # noqa: ANN401
        """Return an object whose ``key`` attribute is a public verification key."""


@dataclass(frozen=True)
class AuthenticatedUser:
    """A principal resolved only after full JWT verification."""

    id: UUID


class JwtVerifier:
    """Verify Supabase-issued tokens and resolve the authenticated user."""

    def __init__(
        self,
        settings: Settings,
        *,
        jwk_client: JWKClient | None = None,
    ) -> None:
        self._settings = settings
        self._jwk_client = jwk_client

    def verify(self, token: str) -> AuthenticatedUser:
        """Return the authenticated user or raise AuthenticationFailed."""
        issuer = self._settings.jwt_issuer_value
        audience = self._settings.jwt_audience
        if not issuer or not audience:
            raise AuthenticationFailed("configuration")

        if self._settings.supabase_jwt_strategy == "hs256":
            secret = self._settings.supabase_jwt_secret
            if secret is None or not secret.get_secret_value().strip():
                raise AuthenticationFailed("configuration")
            key: Any = secret.get_secret_value()
            algorithms = ["HS256"]
        else:
            jwks_url = self._settings.supabase_jwks_url_value
            if not jwks_url:
                raise AuthenticationFailed("configuration")
            client = self._jwk_client or PyJWKClient(jwks_url, cache_keys=True)
            try:
                signing_key = client.get_signing_key_from_jwt(token)
                key = signing_key.key
            except Exception as exc:
                # Never log provider errors: they may echo tokens or URLs with credentials.
                raise AuthenticationFailed("key_unavailable") from exc
            algorithms = ["RS256"]

        try:
            claims = jwt.decode(
                token,
                key=key,
                algorithms=algorithms,
                audience=audience,
                issuer=issuer,
                leeway=self._settings.jwt_leeway_seconds,
                options={"require": _REQUIRED_CLAIMS},
            )
        except jwt.ExpiredSignatureError as exc:
            raise AuthenticationFailed("expired") from exc
        except jwt.InvalidIssuerError as exc:
            raise AuthenticationFailed("invalid_issuer") from exc
        except jwt.InvalidAudienceError as exc:
            raise AuthenticationFailed("invalid_audience") from exc
        except jwt.MissingRequiredClaimError as exc:
            raise AuthenticationFailed("missing_claim") from exc
        except jwt.InvalidTokenError as exc:
            raise AuthenticationFailed("invalid_token") from exc

        try:
            user_id = UUID(str(claims["sub"]))
        except (TypeError, ValueError) as exc:
            raise AuthenticationFailed("invalid_subject") from exc

        return AuthenticatedUser(id=user_id)


def get_jwt_verifier(request: Request) -> JwtVerifier:
    """Return a verifier cached on the application instance."""
    verifier = getattr(request.app.state, "jwt_verifier", None)
    if verifier is None:
        settings: Settings = request.app.state.settings
        verifier = JwtVerifier(settings)
        request.app.state.jwt_verifier = verifier
    return verifier


async def get_current_user(request: Request) -> AuthenticatedUser:
    """FastAPI dependency that resolves a user from a verified Bearer token."""
    header = request.headers.get("Authorization", "")
    parts = header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        log_event(logger, logging.WARNING, "auth_header_failed", reason="missing_bearer")
        raise AppError(
            status_code=401,
            code="UNAUTHORIZED",
            message="Invalid or expired credentials.",
        )

    try:
        user = get_jwt_verifier(request).verify(parts[1])
    except AuthenticationFailed as exc:
        log_event(logger, logging.WARNING, "jwt_verification_failed", reason=exc.reason)
        raise AppError(
            status_code=401,
            code="UNAUTHORIZED",
            message="Invalid or expired credentials.",
        ) from None
    return user
