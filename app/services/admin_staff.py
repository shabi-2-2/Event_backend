"""Event-scoped staff membership administration."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import StaffMembership
from app.db.models.common import StaffRole
from app.schemas.admin import Page, StaffResponse
from app.services.admin_common import (
    add_audit,
    as_utc,
    conflict,
    log_admin_action,
    mutation_transaction,
    not_found,
    paginate,
    with_row_lock,
)


def _response(membership: StaffMembership) -> StaffResponse:
    return StaffResponse(
        user_id=membership.user_id,
        role=membership.role,
        created_at=as_utc(membership.created_at),
    )


def list_staff(
    session: Session,
    *,
    event_id: UUID,
    page: int,
    page_size: int,
    role: StaffRole | None,
) -> Page[StaffResponse]:
    """Return a paginated staff listing."""

    statement = select(StaffMembership).where(StaffMembership.event_id == event_id)
    if role is not None:
        statement = statement.where(StaffMembership.role == role)
    statement = statement.order_by(StaffMembership.created_at.asc(), StaffMembership.user_id.asc())
    rows, total = paginate(session, statement, page=page, page_size=page_size)
    return Page[StaffResponse](
        items=[_response(row[0]) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
    )


def _admin_count(session: Session, event_id: UUID, *, lock: bool) -> int:
    statement = select(StaffMembership).where(
        StaffMembership.event_id == event_id,
        StaffMembership.role == StaffRole.ADMIN,
    )
    if lock:
        statement = with_row_lock(statement, session, StaffMembership)
    return len(session.scalars(statement).all())


def add_staff(
    session: Session,
    *,
    event_id: UUID,
    user_id: UUID,
    role: StaffRole,
    actor_user_id: UUID,
) -> StaffResponse:
    """Assign an existing Supabase Auth user an event-scoped role."""

    membership = StaffMembership(user_id=user_id, event_id=event_id, role=role)
    try:
        with mutation_transaction(session):
            existing = session.get(StaffMembership, (user_id, event_id))
            if existing is not None:
                raise conflict("This user already has a staff role for the event.")
            session.add(membership)
            add_audit(
                session,
                event_id=event_id,
                actor_user_id=actor_user_id,
                action="staff.added",
                target_type="staff_membership",
                target_id=str(user_id),
                context={"role": role.value},
            )
            session.flush()
    except IntegrityError as exc:
        raise conflict("This user already has a staff role for the event.") from exc
    log_admin_action("staff.added", event_id=event_id, actor_user_id=actor_user_id)
    return _response(membership)


def change_staff_role(
    session: Session,
    *,
    event_id: UUID,
    user_id: UUID,
    role: StaffRole,
    actor_user_id: UUID,
) -> StaffResponse:
    """Change a staff role while preserving at least one active admin."""

    with mutation_transaction(session):
        membership = session.scalar(
            with_row_lock(
                select(StaffMembership).where(
                    StaffMembership.event_id == event_id,
                    StaffMembership.user_id == user_id,
                ),
                session,
                StaffMembership,
            )
        )
        if membership is None:
            raise not_found("Staff membership was not found for this event.")
        if membership.role == role:
            return _response(membership)
        if (
            membership.role == StaffRole.ADMIN
            and role != StaffRole.ADMIN
            and _admin_count(session, event_id, lock=True) <= 1
        ):
            raise conflict(
                "The final event administrator cannot be demoted.",
                code="FINAL_ADMIN",
            )
        previous = membership.role
        membership.role = role
        add_audit(
            session,
            event_id=event_id,
            actor_user_id=actor_user_id,
            action="staff.role_changed",
            target_type="staff_membership",
            target_id=str(user_id),
            context={"previous_role": previous.value, "role": role.value},
        )
        session.flush()
        response = _response(membership)

    log_admin_action("staff.role_changed", event_id=event_id, actor_user_id=actor_user_id)
    return response


def remove_staff(
    session: Session,
    *,
    event_id: UUID,
    user_id: UUID,
    actor_user_id: UUID,
) -> None:
    """Remove a staff membership while preserving the final event admin."""

    with mutation_transaction(session):
        membership = session.scalar(
            with_row_lock(
                select(StaffMembership).where(
                    StaffMembership.event_id == event_id,
                    StaffMembership.user_id == user_id,
                ),
                session,
                StaffMembership,
            )
        )
        if membership is None:
            raise not_found("Staff membership was not found for this event.")
        if membership.role == StaffRole.ADMIN and _admin_count(session, event_id, lock=True) <= 1:
            raise conflict(
                "The final event administrator cannot be removed.",
                code="FINAL_ADMIN",
            )
        add_audit(
            session,
            event_id=event_id,
            actor_user_id=actor_user_id,
            action="staff.removed",
            target_type="staff_membership",
            target_id=str(user_id),
            context={"role": membership.role.value},
        )
        session.delete(membership)
        session.flush()

    log_admin_action("staff.removed", event_id=event_id, actor_user_id=actor_user_id)
