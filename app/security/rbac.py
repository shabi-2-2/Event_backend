"""Event-scoped role-based access control using staff memberships."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.logging import get_logger, log_event
from app.db.models import StaffMembership
from app.db.models.common import StaffRole
from app.db.session import get_session
from app.security.exceptions import AuthorizationDenied
from app.security.jwt import AuthenticatedUser, get_current_user

logger = get_logger(__name__)


class Permission(StrEnum):
    EVENT_MANAGE = "event.manage"
    ATTENDEE_MANAGE = "attendee.manage"
    TICKET_MANAGE = "ticket.manage"
    ATTENDANCE_EXPORT = "attendance.export"
    STAFF_MANAGE = "staff.manage"
    TICKET_VERIFY = "ticket.verify"
    TICKET_CHECKIN = "ticket.checkin"
    ATTENDEE_VIEW = "attendee.view"
    ATTENDEE_VIEW_CHECKIN = "attendee.view.checkin"
    EVENT_STATS_VIEW = "event.stats.view"


_ADMIN = StaffRole.ADMIN
_CHECKIN = StaffRole.CHECKIN
_VIEWER = StaffRole.VIEWER

_ROLE_MAP: dict[Permission, tuple[StaffRole, ...]] = {
    Permission.EVENT_MANAGE: (_ADMIN,),
    Permission.ATTENDEE_MANAGE: (_ADMIN,),
    Permission.TICKET_MANAGE: (_ADMIN,),
    Permission.ATTENDANCE_EXPORT: (_ADMIN,),
    Permission.STAFF_MANAGE: (_ADMIN,),
    Permission.TICKET_VERIFY: (_ADMIN, _CHECKIN),
    Permission.TICKET_CHECKIN: (_ADMIN, _CHECKIN),
    Permission.ATTENDEE_VIEW: (_ADMIN, _VIEWER),
    Permission.ATTENDEE_VIEW_CHECKIN: (_ADMIN, _CHECKIN),
    Permission.EVENT_STATS_VIEW: (_ADMIN, _VIEWER),
}


@dataclass(frozen=True)
class EventAccess:
    """The verified principal, event, role, and permission for one request."""

    user_id: UUID
    event_id: UUID
    role: StaffRole
    permission: Permission


def roles_for(permission: Permission) -> tuple[StaffRole, ...]:
    """Return the roles allowed for a permission; unknown permissions deny."""
    return _ROLE_MAP.get(permission, ())


def authorize_event_access(
    session: Session,
    user: AuthenticatedUser,
    event_id: UUID,
    permission: Permission,
) -> EventAccess | None:
    """Return access details only when an event-scoped membership allows it."""
    roles = roles_for(permission)
    if not roles:
        return None

    membership = session.execute(
        select(StaffMembership).where(
            StaffMembership.user_id == user.id,
            StaffMembership.event_id == event_id,
            StaffMembership.role.in_(roles),
        )
    ).scalar_one_or_none()
    if membership is None:
        return None

    return EventAccess(
        user_id=user.id,
        event_id=event_id,
        role=membership.role,
        permission=permission,
    )


def _event_id_from_request(request: Request) -> UUID:
    raw = request.path_params.get("event_id") or request.query_params.get("event_id")
    if not raw:
        raise AuthorizationDenied("missing_event_id")
    try:
        return UUID(str(raw))
    except ValueError as exc:
        raise AuthorizationDenied("invalid_event_id") from exc


def require_permission(permission: Permission) -> Callable[..., Any]:
    """Build a FastAPI dependency that enforces an event-scoped permission.

    The event identifier is read from the route's ``event_id`` path parameter
    (or query parameter), so no user or event identifiers are hardcoded.
    """

    async def dependency(
        request: Request,
        user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
        session: Session = Depends(get_session),  # noqa: B008
    ) -> EventAccess:
        try:
            event_id = _event_id_from_request(request)
            access = authorize_event_access(session, user, event_id, permission)
            if access is None:
                raise AuthorizationDenied()
        except AuthorizationDenied as exc:
            log_event(
                logger,
                logging.WARNING,
                "rbac_denied",
                reason=exc.reason,
                permission=getattr(permission, "value", str(permission)),
            )
            raise AppError(
                status_code=403,
                code="FORBIDDEN",
                message="You do not have access to this resource.",
            ) from None
        return access

    return dependency
