"""Database-backed event-scoped RBAC tests."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.models import Event, StaffMembership
from app.db.models.common import StaffRole
from app.db.session import get_session
from app.main import create_app
from app.security.jwt import AuthenticatedUser, get_current_user
from app.security.rbac import EventAccess, Permission, require_permission

pytestmark = pytest.mark.postgres

_USER_ID = uuid4()


@pytest.fixture
def rbac_harness(
    migrated_postgres: Engine,
) -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    factory = sessionmaker(bind=migrated_postgres, autoflush=False, expire_on_commit=False)

    def reset() -> None:
        with factory() as session:
            session.execute(delete(StaffMembership))
            session.execute(delete(Event))
            session.commit()

    reset()

    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+pysqlite:///:memory:",
    )
    app = create_app(settings)

    def fake_current_user() -> AuthenticatedUser:
        return AuthenticatedUser(id=_USER_ID)

    def fake_session() -> Iterator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_current_user] = fake_current_user
    app.dependency_overrides[get_session] = fake_session

    def add_route(path: str, permission: Permission) -> None:
        @app.get(path)
        async def route(
            access: EventAccess = Depends(require_permission(permission)),  # noqa: B008
        ) -> dict[str, str]:
            return {"role": access.role.value, "event_id": str(access.event_id)}

    add_route("/_test/events/{event_id}/admin", Permission.EVENT_MANAGE)
    add_route("/_test/events/{event_id}/checkin", Permission.TICKET_VERIFY)
    add_route("/_test/events/{event_id}/viewer", Permission.EVENT_STATS_VIEW)
    add_route("/_test/events/{event_id}/export", Permission.ATTENDANCE_EXPORT)

    with TestClient(app) as client:
        yield client, factory

    app.dependency_overrides.clear()
    reset()


def create_event(factory: sessionmaker[Session]) -> UUID:
    with factory() as session:
        event = Event(
            slug=f"rbac-event-{uuid4().hex[:10]}",
            name="RBAC Event",
            starts_at=datetime(2026, 9, 1, 9, tzinfo=UTC),
            ends_at=datetime(2026, 9, 1, 18, tzinfo=UTC),
            timezone="UTC",
        )
        session.add(event)
        session.commit()
        return event.id


def add_membership(
    factory: sessionmaker[Session], event_id: UUID, role: StaffRole, *, user_id: UUID | None = None
) -> None:
    with factory() as session:
        session.add(
            StaffMembership(
                user_id=user_id or _USER_ID,
                event_id=event_id,
                role=role,
            )
        )
        session.commit()


def test_admin_has_full_event_access(
    rbac_harness: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = rbac_harness
    event_id = create_event(factory)
    add_membership(factory, event_id, StaffRole.ADMIN)

    response = client.get(f"/_test/events/{event_id}/admin")
    export_response = client.get(f"/_test/events/{event_id}/export")

    assert response.status_code == 200, response.json()
    assert response.json() == {"role": "admin", "event_id": str(event_id)}
    assert export_response.status_code == 200


def test_checkin_role_can_verify_tickets_but_not_export(
    rbac_harness: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = rbac_harness
    event_id = create_event(factory)
    add_membership(factory, event_id, StaffRole.CHECKIN)

    checkin_response = client.get(f"/_test/events/{event_id}/checkin")
    export_response = client.get(f"/_test/events/{event_id}/export")

    assert checkin_response.status_code == 200
    assert checkin_response.json()["role"] == "checkin"
    assert export_response.status_code == 403


def test_viewer_can_read_stats_but_not_check_in(
    rbac_harness: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = rbac_harness
    event_id = create_event(factory)
    add_membership(factory, event_id, StaffRole.VIEWER)

    viewer_response = client.get(f"/_test/events/{event_id}/viewer")
    checkin_response = client.get(f"/_test/events/{event_id}/checkin")

    assert viewer_response.status_code == 200
    assert viewer_response.json()["role"] == "viewer"
    assert checkin_response.status_code == 403


def test_missing_membership_is_denied(
    rbac_harness: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = rbac_harness
    event_id = create_event(factory)

    response = client.get(f"/_test/events/{event_id}/admin")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_membership_for_another_event_is_denied(
    rbac_harness: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = rbac_harness
    requested_event = create_event(factory)
    other_event = create_event(factory)
    add_membership(factory, other_event, StaffRole.ADMIN)

    response = client.get(f"/_test/events/{requested_event}/admin")

    assert response.status_code == 403


def test_viewer_cannot_escalate_to_admin_permission(
    rbac_harness: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = rbac_harness
    event_id = create_event(factory)
    add_membership(factory, event_id, StaffRole.VIEWER)

    response = client.get(f"/_test/events/{event_id}/admin")

    assert response.status_code == 403


def test_jwt_subject_is_not_trusted_as_membership(
    rbac_harness: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = rbac_harness
    event_id = create_event(factory)
    add_membership(factory, event_id, StaffRole.ADMIN, user_id=uuid4())

    response = client.get(f"/_test/events/{event_id}/admin")

    assert response.status_code == 403
