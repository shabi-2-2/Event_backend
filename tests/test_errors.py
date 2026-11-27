"""Global exception handling tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.errors import AppError


def test_not_found_uses_standard_error_shape(client: TestClient) -> None:
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "NOT_FOUND",
            "message": "The requested resource was not found.",
        }
    }
    assert "X-Correlation-ID" in response.headers


def test_app_error_uses_standard_error_shape(app) -> None:
    @app.get("/_test/conflict")
    async def _conflict() -> None:
        raise AppError(status_code=409, code="TEST_CONFLICT", message="Conflict")

    with TestClient(app) as client:
        response = client.get("/_test/conflict")

    assert response.status_code == 409
    assert response.json() == {"error": {"code": "TEST_CONFLICT", "message": "Conflict"}}


def test_validation_error_does_not_reflect_submitted_values(app) -> None:
    @app.get("/_test/validation")
    async def _validation(limit: int, email: str | None = None) -> None:
        return None

    with TestClient(app) as client:
        response = client.get(
            "/_test/validation",
            params={"limit": "not-an-int", "email": "pii@example.com"},
        )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "pii@example.com" not in response.text
    assert all("input" not in detail for detail in body["error"]["details"])


def test_unhandled_error_returns_generic_response(app) -> None:
    @app.get("/_test/boom")
    async def _boom() -> None:
        raise RuntimeError("pii@example.com must not leak")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/_test/boom")

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected error occurred.",
        }
    }
    assert "pii@example.com" not in response.text
