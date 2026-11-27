"""Application lifespan and database foundation tests."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import Settings
from app.db.session import create_db_engine, create_session_factory
from app.main import create_app


def test_application_startup_and_shutdown(settings: Settings) -> None:
    application = create_app(settings)
    assert application.state.started_at is None
    assert application.state.shutdown_at is None

    with TestClient(application) as client:
        assert application.state.started_at is not None
        assert application.state.shutdown_at is None
        assert application.state.engine is not None
        assert application.state.session_factory is not None
        assert client.get("/health").status_code == 200

    assert application.state.shutdown_at is not None


def test_session_factory_opens_working_session(settings: Settings) -> None:
    engine = create_db_engine(settings)
    factory = create_session_factory(engine)
    try:
        with factory() as session:
            assert session.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        engine.dispose()
