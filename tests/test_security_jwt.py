"""Supabase JWT verification tests."""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Annotated
from uuid import UUID, uuid4

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings
from app.main import create_app
from app.security.exceptions import AuthenticationFailed
from app.security.jwt import AuthenticatedUser, JwtVerifier, get_current_user

_SQLITE_URL = "sqlite+pysqlite:///:memory:"
_SECRET = "jwt-hs256-test-secret"
_ISSUER = "https://project.example.supabase.co/auth/v1"
_AUDIENCE = "authenticated"
_USER_ID = uuid4()

_RSA_V1 = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_RSA_V2 = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def hs_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "supabase_jwt_strategy": "hs256",
        "supabase_jwt_secret": SecretStr(_SECRET),
        "jwt_issuer": _ISSUER,
        "jwt_audience": _AUDIENCE,
    }
    values.update(overrides)
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=_SQLITE_URL,
        **values,  # type: ignore[arg-type]
    )


def jwt_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "supabase_jwt_strategy": "jwks",
        "supabase_jwks_url": "https://project.example.supabase.co/auth/v1/.well-known/jwks.json",
        "jwt_issuer": _ISSUER,
        "jwt_audience": _AUDIENCE,
    }
    values.update(overrides)
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=_SQLITE_URL,
        **values,  # type: ignore[arg-type]
    )


def make_hs_token(
    *,
    secret: str = _SECRET,
    issuer: str = _ISSUER,
    audience: str = _AUDIENCE,
    omit: set[str] | None = None,
    subject: str = str(_USER_ID),
    expires_in: int = 300,
) -> str:
    now = int(time.time())
    payload: dict[str, object] = {
        "sub": subject,
        "iss": issuer,
        "aud": audience,
        "iat": now,
        "exp": now + expires_in,
    }
    for key in omit or set():
        payload.pop(key, None)
    return jwt.encode(payload, secret, algorithm="HS256")


def make_rsa_token(*, private_key: rsa.RSAPrivateKey, kid: str) -> str:
    now = int(time.time())
    payload = {
        "sub": str(_USER_ID),
        "iss": _ISSUER,
        "aud": _AUDIENCE,
        "iat": now,
        "exp": now + 300,
    }
    return jwt.encode(
        payload,
        private_key,
        algorithm="RS256",
        headers={"kid": kid},
    )


class FakeJWKClient:
    """Stand-in for the Supabase JWKS endpoint with a rotating key set."""

    def __init__(self, keys: dict[str, rsa.RSAPrivateKey]) -> None:
        self._keys = keys

    def get_signing_key_from_jwt(self, token: str) -> SimpleNamespace:
        kid = str(jwt.get_unverified_header(token).get("kid"))
        if kid not in self._keys:
            raise KeyError(kid)
        return SimpleNamespace(key=self._keys[kid].public_key())


def test_valid_hs256_token_resolves_authenticated_user() -> None:
    verifier = JwtVerifier(hs_settings())

    user = verifier.verify(make_hs_token())

    assert user == AuthenticatedUser(id=_USER_ID)
    assert isinstance(user.id, UUID)


def test_invalid_signature_is_rejected() -> None:
    verifier = JwtVerifier(hs_settings())

    try:
        verifier.verify(make_hs_token(secret="wrong-secret"))
    except AuthenticationFailed as exc:
        assert exc.reason == "invalid_token"
    else:
        raise AssertionError("invalid signature was accepted")


def test_expired_token_is_rejected() -> None:
    verifier = JwtVerifier(hs_settings())

    try:
        verifier.verify(make_hs_token(expires_in=-60))
    except AuthenticationFailed as exc:
        assert exc.reason == "expired"
    else:
        raise AssertionError("expired token was accepted")


def test_invalid_issuer_and_audience_are_rejected() -> None:
    verifier = JwtVerifier(hs_settings())

    for token, expected_reason in (
        (make_hs_token(issuer="https://evil.example/auth/v1"), "invalid_issuer"),
        (make_hs_token(audience="other-audience"), "invalid_audience"),
    ):
        try:
            verifier.verify(token)
        except AuthenticationFailed as exc:
            assert exc.reason == expected_reason
        else:
            raise AssertionError(f"{expected_reason} was not rejected")


def test_missing_claims_and_malformed_tokens_are_rejected() -> None:
    verifier = JwtVerifier(hs_settings())

    for token in (
        make_hs_token(omit={"exp"}),
        make_hs_token(omit={"sub"}),
        "not-a-jwt",
    ):
        try:
            verifier.verify(token)
        except AuthenticationFailed as exc:
            assert exc.reason in {"missing_claim", "invalid_token"}
        else:
            raise AssertionError("malformed token was accepted")


def test_invalid_subject_claim_is_rejected() -> None:
    verifier = JwtVerifier(hs_settings())

    try:
        verifier.verify(make_hs_token(subject="not-a-uuid"))
    except AuthenticationFailed as exc:
        assert exc.reason == "invalid_subject"
    else:
        raise AssertionError("non-UUID subject was accepted")


def test_missing_key_configuration_fails_closed() -> None:
    settings = hs_settings(supabase_jwt_secret=None)

    try:
        JwtVerifier(settings).verify(make_hs_token())
    except AuthenticationFailed as exc:
        assert exc.reason == "configuration"
    else:
        raise AssertionError("verification succeeded without a configured secret")


def test_jwks_key_rotation_is_supported() -> None:
    client = FakeJWKClient({"v1": _RSA_V1, "v2": _RSA_V2})
    verifier = JwtVerifier(jwt_settings(), jwk_client=client)

    old_user = verifier.verify(make_rsa_token(private_key=_RSA_V1, kid="v1"))
    new_user = verifier.verify(make_rsa_token(private_key=_RSA_V2, kid="v2"))

    assert old_user.id == _USER_ID
    assert new_user.id == _USER_ID


def test_unknown_jwks_key_id_is_rejected() -> None:
    client = FakeJWKClient({"v1": _RSA_V1})
    verifier = JwtVerifier(jwt_settings(), jwk_client=client)

    try:
        verifier.verify(make_rsa_token(private_key=_RSA_V2, kid="v2"))
    except AuthenticationFailed as exc:
        assert exc.reason == "key_unavailable"
    else:
        raise AssertionError("unknown JWKS key was accepted")


def test_bearer_dependency_uses_verified_user() -> None:
    app = create_app(hs_settings())

    @app.get("/_test/me")
    async def me(
        user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    ) -> dict[str, str]:
        return {"sub": str(user.id)}

    with TestClient(app) as client:
        valid = client.get("/_test/me", headers={"Authorization": f"Bearer {make_hs_token()}"})
        invalid = client.get("/_test/me", headers={"Authorization": "Basic abc"})

    assert valid.status_code == 200
    assert valid.json() == {"sub": str(_USER_ID)}
    assert invalid.status_code == 401
