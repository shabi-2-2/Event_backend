"""Portable RBAC default-deny tests that do not require PostgreSQL."""

from __future__ import annotations

from typing import cast
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models.common import StaffRole
from app.security.jwt import AuthenticatedUser
from app.security.rbac import Permission, authorize_event_access, roles_for


def test_known_permissions_have_explicit_role_mappings() -> None:
    assert all(roles_for(permission) for permission in Permission)
    assert StaffRole.ADMIN in roles_for(Permission.EVENT_MANAGE)
    assert StaffRole.CHECKIN in roles_for(Permission.TICKET_VERIFY)
    assert StaffRole.VIEWER in roles_for(Permission.EVENT_STATS_VIEW)


def test_unknown_permission_denies_by_default() -> None:
    unknown = cast(Permission, "unknown.permission")

    assert roles_for(unknown) == ()
    assert (
        authorize_event_access(
            cast(Session, None),
            AuthenticatedUser(id=uuid4()),
            uuid4(),
            unknown,
        )
        is None
    )
