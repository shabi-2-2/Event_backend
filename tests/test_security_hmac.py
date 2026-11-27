"""Webhook HMAC authentication tests."""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Annotated

from fastapi import Depends, Request
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings
from app.main import create_app
from app.security.webhook import WEBHOOK_PATH, WebhookIdentity, require_webhook_auth

_SQLITE_URL = "sqlite+pysqlite:///:memory:"
_V1_SECRET = "v1-super-secret-value"
_V2_SECRET = "v2-super-secret-value"


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "webhook_signing_keys": {
            "v1": SecretStr(_V1_SECRET),
        }
    }
    values.update(overrides)
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=_SQLITE_URL,
        **values,  # type: ignore[arg-type]
    )


def sign_body(body: bytes, timestamp: str, secret: str) -> str:
    message = f"{timestamp}.POST.{WEBHOOK_PATH}.".encode() + body
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def make_client(settings: Settings) -> TestClient:
    app = create_app(settings)

    @app.post("/_test/webhook-auth")
    async def endpoint(
        request: Request,
        identity: Annotated[WebhookIdentity, Depends(require_webhook_auth)],
    ) -> dict[str, object]:
        payload = await request.json()
        return {"key_id": identity.key_id, "received": payload["ok"]}

    return TestClient(app)


def auth_headers(key_id: str, timestamp: str, signature: str) -> dict[str, str]:
    return {
        "X-Webhook-Key-Id": key_id,
        "X-Webhook-Timestamp": timestamp,
        "X-Webhook-Signature": signature,
    }


def test_valid_signature_is_accepted() -> None:
    body = b'{"ok": true}'
    timestamp = str(int(time.time()))
    signature = sign_body(body, timestamp, _V1_SECRET)

    response = make_client(make_settings()).post(
        "/_test/webhook-auth",
        content=body,
        headers=auth_headers("v1", timestamp, signature),
    )

    assert response.status_code == 200
    assert response.json() == {"key_id": "v1", "received": True}


def test_signature_with_sha256_prefix_is_accepted() -> None:
    body = b'{"ok": true}'
    timestamp = str(int(time.time()))
    signature = f"sha256={sign_body(body, timestamp, _V1_SECRET)}"

    response = make_client(make_settings()).post(
        "/_test/webhook-auth",
        content=body,
        headers=auth_headers("v1", timestamp, signature),
    )

    assert response.status_code == 200


def test_invalid_signature_is_rejected() -> None:
    body = b'{"ok": true}'
    timestamp = str(int(time.time()))

    response = make_client(make_settings()).post(
        "/_test/webhook-auth",
        content=body,
        headers=auth_headers("v1", timestamp, "0" * 64),
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_missing_headers_are_rejected() -> None:
    body = b'{"ok": true}'
    timestamp = str(int(time.time()))

    response = make_client(make_settings()).post(
        "/_test/webhook-auth",
        content=body,
        headers={"X-Webhook-Key-Id": "v1", "X-Webhook-Timestamp": timestamp},
    )

    assert response.status_code == 401


def test_expired_and_future_timestamps_are_rejected() -> None:
    body = b'{"ok": true}'
    now = int(time.time())
    client = make_client(make_settings())

    for timestamp in (str(now - 400), str(now + 400)):
        response = client.post(
            "/_test/webhook-auth",
            content=body,
            headers=auth_headers("v1", timestamp, sign_body(body, timestamp, _V1_SECRET)),
        )
        assert response.status_code == 401


def test_unknown_key_id_is_rejected() -> None:
    body = b'{"ok": true}'
    timestamp = str(int(time.time()))

    response = make_client(make_settings()).post(
        "/_test/webhook-auth",
        content=body,
        headers=auth_headers("v9", timestamp, sign_body(body, timestamp, _V1_SECRET)),
    )

    assert response.status_code == 401


def test_secret_rotation_accepts_old_and_new_key_ids() -> None:
    settings = make_settings(
        webhook_signing_keys={
            "v1": SecretStr(_V1_SECRET),
            "v2": SecretStr(_V2_SECRET),
        }
    )
    client = make_client(settings)
    body = b'{"ok": true}'
    timestamp = str(int(time.time()))

    old_response = client.post(
        "/_test/webhook-auth",
        content=body,
        headers=auth_headers("v1", timestamp, sign_body(body, timestamp, _V1_SECRET)),
    )
    new_response = client.post(
        "/_test/webhook-auth",
        content=body,
        headers=auth_headers("v2", timestamp, sign_body(body, timestamp, _V2_SECRET)),
    )

    assert old_response.json()["key_id"] == "v1"
    assert new_response.json()["key_id"] == "v2"


def test_tampered_body_is_rejected() -> None:
    signed_body = b'{"ok": true}'
    sent_body = b'{"ok": false}'
    timestamp = str(int(time.time()))

    response = make_client(make_settings()).post(
        "/_test/webhook-auth",
        content=sent_body,
        headers=auth_headers("v1", timestamp, sign_body(signed_body, timestamp, _V1_SECRET)),
    )

    assert response.status_code == 401


def test_no_configured_secret_fails_closed() -> None:
    body = b'{"ok": true}'
    timestamp = str(int(time.time()))

    response = make_client(make_settings(webhook_signing_keys={})).post(
        "/_test/webhook-auth",
        content=body,
        headers=auth_headers("v1", timestamp, sign_body(body, timestamp, _V1_SECRET)),
    )

    assert response.status_code == 401


def test_failed_auth_does_not_log_secret_signature_or_body(capsys) -> None:
    body = b'{"ok": true, "submission_id": "secret-submission"}'
    timestamp = str(int(time.time()))
    signature = sign_body(body, timestamp, _V1_SECRET)

    make_client(make_settings()).post(
        "/_test/webhook-auth",
        content=body,
        headers=auth_headers("v1", timestamp, signature),
    )

    output = capsys.readouterr().out
    assert _V1_SECRET not in output
    assert signature not in output
    assert "secret-submission" not in output
