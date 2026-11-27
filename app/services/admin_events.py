"""Event lifecycle management for administrators."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import Event, StaffMembership
from app.db.models.common import EventStatus, StaffRole
from app.schemas.admin import (
    EventCreate,
    EventResponse,
    EventUpdate,
    Page,
    validate_event_times,
)
from app.services.admin_common import (
    add_audit,
    conflict,
    log_admin_action,
    mutation_transaction,
    not_found,
    paginate,
)


def _response(event: Event) -> EventResponse:
    return EventResponse(
        slug=event.slug,
        name=event.name,
        description=event.description,
        starts_at=event.starts_at,
        ends_at=event.ends_at,
        timezone=event.timezone,
        venue=event.venue,
        capacity=event.capacity,
        registration_opens_at=event.registration_opens_at,
        registration_closes_at=event.registration_closes_at,
        status=event.status,
        created_at=event.created_at,
        updated_at=event.updated_at,
    )


def _get_event(
    session: Session,
    slug: str,
    *,
    event_id: UUID | None = None,
) -> Event | None:
    statement = select(Event).where(Event.slug == slug.strip().lower())
    if event_id is not None:
        statement = statement.where(Event.id == event_id)
    return session.scalar(statement)


def create_event(
    session: Session,
    payload: EventCreate,
    *,
    actor_user_id: UUID,
) -> EventResponse:
    """Create a draft event and make the creator its first admin."""

    values = payload.model_dump()
    event = Event(
        slug=values["slug"],
        name=values["name"],
        description=values["description"],
        starts_at=values["starts_at"],
        ends_at=values["ends_at"],
        timezone=values["timezone"],
        venue=values["venue"],
        capacity=values["capacity"],
        registration_opens_at=values["registration_opens_at"],
        registration_closes_at=values["registration_closes_at"],
        status=EventStatus.DRAFT,
    )
    try:
        with mutation_transaction(session):
            session.add(event)
            session.flush()
            session.add(
                StaffMembership(
                    user_id=actor_user_id,
                    event_id=event.id,
                    role=StaffRole.ADMIN,
                )
            )
            add_audit(
                session,
                event_id=event.id,
                actor_user_id=actor_user_id,
                action="event.created",
                target_type="event",
                target_id=event.slug,
                context={"status": EventStatus.DRAFT.value},
            )
            session.flush()
    except IntegrityError as exc:
        raise conflict("An event with this slug already exists.", code="SLUG_CONFLICT") from exc
    log_admin_action("event.created", event_id=event.id, actor_user_id=actor_user_id)
    return _response(event)


def list_events(
    session: Session,
    *,
    page: int,
    page_size: int,
    status: EventStatus | None = None,
) -> Page[EventResponse]:
    """Return a paginated event listing with stable ordering."""

    statement = select(Event)
    if status is not None:
        statement = statement.where(Event.status == status)
    statement = statement.order_by(Event.created_at.desc(), Event.slug.asc())
    rows, total = paginate(session, statement, page=page, page_size=page_size)
    return Page[EventResponse](
        items=[_response(row[0]) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
    )


def get_event(session: Session, *, slug: str, event_id: UUID) -> EventResponse:
    """Return one event scoped to the caller's membership."""

    event = _get_event(session, slug, event_id=event_id)
    if event is None:
        raise not_found()
    return _response(event)


def update_event(
    session: Session,
    payload: EventUpdate,
    *,
    slug: str,
    event_id: UUID,
    actor_user_id: UUID,
) -> EventResponse:
    """Apply a partial event update without changing lifecycle status."""

    event = _get_event(session, slug, event_id=event_id)
    if event is None:
        raise not_found()
    values = payload.model_dump(exclude_unset=True)
    prospective = {
        "starts_at": values.get("starts_at", event.starts_at),
        "ends_at": values.get("ends_at", event.ends_at),
        "registration_opens_at": values.get("registration_opens_at", event.registration_opens_at),
        "registration_closes_at": values.get(
            "registration_closes_at", event.registration_closes_at
        ),
    }
    try:
        validate_event_times(
            prospective["starts_at"],
            prospective["ends_at"],
            prospective["registration_opens_at"],
            prospective["registration_closes_at"],
        )
    except ValueError as exc:
        raise AppError(status_code=422, code="VALIDATION_ERROR", message=str(exc)) from exc
    for key, value in values.items():
        setattr(event, key, value)
    changed_fields = sorted(values)
    with mutation_transaction(session):
        if changed_fields:
            add_audit(
                session,
                event_id=event.id,
                actor_user_id=actor_user_id,
                action="event.updated",
                target_type="event",
                target_id=event.slug,
                context={"fields": changed_fields},
            )
    log_admin_action("event.updated", event_id=event.id, actor_user_id=actor_user_id)
    return _response(event)


def _transition(
    session: Session,
    *,
    slug: str,
    event_id: UUID,
    actor_user_id: UUID,
    allowed_from: tuple[EventStatus, ...],
    target: EventStatus,
    action: str,
) -> EventResponse:
    event = _get_event(session, slug, event_id=event_id)
    if event is None:
        raise not_found()
    if event.status not in allowed_from:
        raise conflict(f"Cannot transition event from {event.status.value} to {target.value}.")
    previous = event.status
    with mutation_transaction(session):
        event.status = target
        add_audit(
            session,
            event_id=event.id,
            actor_user_id=actor_user_id,
            action=action,
            target_type="event",
            target_id=event.slug,
            context={"from_status": previous.value, "to_status": target.value},
        )
    log_admin_action(action, event_id=event.id, actor_user_id=actor_user_id)
    return _response(event)


def publish_event(
    session: Session,
    *,
    slug: str,
    event_id: UUID,
    actor_user_id: UUID,
) -> EventResponse:
    """Publish a draft event; archived and cancelled events stay closed."""

    return _transition(
        session,
        slug=slug,
        event_id=event_id,
        actor_user_id=actor_user_id,
        allowed_from=(EventStatus.DRAFT,),
        target=EventStatus.PUBLISHED,
        action="event.published",
    )


def archive_event(
    session: Session,
    *,
    slug: str,
    event_id: UUID,
    actor_user_id: UUID,
) -> EventResponse:
    """Archive a published event without allowing a later silent reopen."""

    return _transition(
        session,
        slug=slug,
        event_id=event_id,
        actor_user_id=actor_user_id,
        allowed_from=(EventStatus.PUBLISHED,),
        target=EventStatus.ARCHIVED,
        action="event.archived",
    )
