"""Health, readiness, versioning, and CORS tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.session import get_db_health
from app.main import create_app


def test_root_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "service": "event-management-api",
    }


def test_api_health(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "service": "event-management-api",
        "api_version": "v1",
        "app_version": "0.1.0",
    }


def test_readiness_reports_database_ready(client: TestClient) -> None:
    response = client.get("/api/v1/ready")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"database": "ready"},
    }


def test_readiness_reports_database_unavailable(app) -> None:
    app.dependency_overrides[get_db_health] = lambda: False
    with TestClient(app) as client:
        response = client.get("/api/v1/ready")
    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"database": "unavailable"},
    }


def test_cors_preflight_for_configured_origin(client: TestClient) -> None:
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://testserver",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://testserver"


def test_docs_can_be_disabled(settings: Settings) -> None:
    application = create_app(settings.model_copy(update={"docs_enabled": False}))
    with TestClient(application) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404
