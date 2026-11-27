"""Administrative event, attendee, operations, and reporting endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models.common import (
    EmailDeliveryStatus,
    EventStatus,
    RegistrationStatus,
    StaffRole,
    TicketStatus,
)
from app.db.session import get_session
from app.schemas.admin import (
    AdminAttendeeResponse,
    AttendanceAnalyticsResponse,
    AttendeeSortField,
    AuditLogResponse,
    CheckinFilterStatus,
    EmailAnalyticsResponse,
    EmailDeliveryResponse,
    EmailRetryResponse,
    EventCreate,
    EventResponse,
    EventUpdate,
    ExportFormat,
    OverviewAnalyticsResponse,
    Page,
    RegistrationAnalyticsResponse,
    RegistrationResponse,
    SortOrder,
    StaffCreateRequest,
    StaffResponse,
    StaffRoleUpdate,
    TicketResendResponse,
    TicketResponse,
    ViewerAttendeeResponse,
)
from app.schemas.eligibility import (
    RosterConfirmRequest,
    RosterCsvRequest,
    RosterEntryResponse,
    RosterImportResponse,
)
from app.security.rate_limit import RateLimitScope, build_subject, enforce_rate_limit
from app.security.rbac import (
    EventAccess,
    GlobalAccess,
    Permission,
    require_global_permission,
    require_permission_by_slug,
)
from app.services import (
    admin_analytics,
    admin_attendees,
    admin_audit,
    admin_email,
    admin_events,
    admin_exports,
    admin_registrations,
    admin_staff,
    admin_tickets,
    eligibility,
)

router = APIRouter(prefix="/admin", tags=["admin"])


# --- Event management ------------------------------------------------------------------


@router.post("/events", response_model=EventResponse, status_code=201)
def create_event(
    payload: EventCreate,
    access: GlobalAccess = Depends(require_global_permission(Permission.EVENT_MANAGE)),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> EventResponse:
    """Create a draft event and assign the creator as its admin."""

    return admin_events.create_event(session, payload, actor_user_id=access.user_id)


@router.get("/events", response_model=Page[EventResponse])
def list_events(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    status: EventStatus | None = None,
    access: GlobalAccess = Depends(require_global_permission(Permission.EVENT_MANAGE)),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> Page[EventResponse]:
    """List events with stable pagination."""

    del access
    return admin_events.list_events(session, page=page, page_size=page_size, status=status)


@router.get("/events/{event_slug}", response_model=EventResponse)
def get_event(
    event_slug: str,
    access: EventAccess = Depends(require_permission_by_slug(Permission.EVENT_MANAGE)),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> EventResponse:
    """Return an event the caller administers."""

    return admin_events.get_event(session, slug=event_slug, event_id=access.event_id)


@router.patch("/events/{event_slug}", response_model=EventResponse)
def update_event(
    event_slug: str,
    payload: EventUpdate,
    access: EventAccess = Depends(require_permission_by_slug(Permission.EVENT_MANAGE)),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> EventResponse:
    """Update mutable event details without changing lifecycle status."""

    return admin_events.update_event(
        session,
        payload,
        slug=event_slug,
        event_id=access.event_id,
        actor_user_id=access.user_id,
    )


@router.post("/events/{event_slug}/publish", response_model=EventResponse)
def publish_event(
    event_slug: str,
    access: EventAccess = Depends(require_permission_by_slug(Permission.EVENT_MANAGE)),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> EventResponse:
    """Publish a draft event."""

    return admin_events.publish_event(
        session,
        slug=event_slug,
        event_id=access.event_id,
        actor_user_id=access.user_id,
    )


@router.post("/events/{event_slug}/archive", response_model=EventResponse)
def archive_event(
    event_slug: str,
    access: EventAccess = Depends(require_permission_by_slug(Permission.EVENT_MANAGE)),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> EventResponse:
    """Archive a published event."""

    return admin_events.archive_event(
        session,
        slug=event_slug,
        event_id=access.event_id,
        actor_user_id=access.user_id,
    )


# --- Attendees -------------------------------------------------------------------------


@router.get(
    "/events/{event_slug}/attendees",
    response_model=Page[AdminAttendeeResponse] | Page[ViewerAttendeeResponse],
)
def list_attendees(
    event_slug: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    search: str | None = Query(default=None, max_length=200),
    urn: str | None = Query(default=None, max_length=64),
    email: str | None = Query(default=None, max_length=255),
    registration_status: RegistrationStatus | None = None,
    ticket_status: TicketStatus | None = None,
    check_in_status: CheckinFilterStatus | None = None,
    sort_by: AttendeeSortField = AttendeeSortField.REGISTERED_AT,
    sort_order: SortOrder = SortOrder.DESC,
    access: EventAccess = Depends(require_permission_by_slug(Permission.ATTENDEE_VIEW)),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> Page[AdminAttendeeResponse] | Page[ViewerAttendeeResponse]:
    """List event attendees with role-specific privacy fields."""

    return admin_attendees.list_attendees(
        session,
        event_id=access.event_id,
        role=access.role,
        page=page,
        page_size=page_size,
        search=search,
        urn=urn,
        email_search=email,
        registration_status=registration_status,
        ticket_status=ticket_status,
        check_in_status=check_in_status,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get(
    "/events/{event_slug}/attendees/{attendee_reference}",
    response_model=AdminAttendeeResponse | ViewerAttendeeResponse,
)
def get_attendee(
    event_slug: str,
    attendee_reference: str,
    access: EventAccess = Depends(require_permission_by_slug(Permission.ATTENDEE_VIEW)),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> AdminAttendeeResponse | ViewerAttendeeResponse:
    """Return one attendee scoped to the event."""

    return admin_attendees.get_attendee(
        session,
        event_id=access.event_id,
        attendee_reference=attendee_reference,
        role=access.role,
    )


# --- Registrations ---------------------------------------------------------------------


@router.get("/events/{event_slug}/registrations", response_model=Page[RegistrationResponse])
def list_registrations(
    event_slug: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    reference: str | None = Query(default=None, max_length=64),
    name: str | None = Query(default=None, max_length=200),
    email: str | None = Query(default=None, max_length=255),
    registration_status: RegistrationStatus | None = None,
    ticket_status: TicketStatus | None = None,
    check_in_status: CheckinFilterStatus | None = None,
    access: EventAccess = Depends(require_permission_by_slug(Permission.REGISTRATION_MANAGE)),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> Page[RegistrationResponse]:
    """List registrations with filters and stable pagination."""

    return admin_registrations.list_registrations(
        session,
        event_id=access.event_id,
        page=page,
        page_size=page_size,
        reference=reference,
        name=name,
        email=email,
        registration_status=registration_status,
        ticket_status=ticket_status,
        check_in_status=check_in_status,
    )


@router.get(
    "/events/{event_slug}/registrations/{registration_reference}",
    response_model=RegistrationResponse,
)
def get_registration(
    event_slug: str,
    registration_reference: str,
    access: EventAccess = Depends(require_permission_by_slug(Permission.REGISTRATION_MANAGE)),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> RegistrationResponse:
    """Return one registration scoped to the event."""

    return admin_registrations.get_registration(
        session,
        event_id=access.event_id,
        registration_reference=registration_reference,
    )


@router.post(
    "/events/{event_slug}/registrations/{registration_reference}/cancel",
    response_model=RegistrationResponse,
)
def cancel_registration(
    event_slug: str,
    registration_reference: str,
    access: EventAccess = Depends(require_permission_by_slug(Permission.REGISTRATION_MANAGE)),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> RegistrationResponse:
    """Cancel a registration and revoke its ticket atomically."""

    return admin_registrations.cancel_registration(
        session,
        event_id=access.event_id,
        registration_reference=registration_reference,
        actor_user_id=access.user_id,
    )


# --- Tickets ---------------------------------------------------------------------------


@router.get("/events/{event_slug}/tickets", response_model=Page[TicketResponse])
def list_tickets(
    event_slug: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    ticket_status: TicketStatus | None = None,
    reference: str | None = Query(default=None, max_length=64),
    access: EventAccess = Depends(require_permission_by_slug(Permission.TICKET_MANAGE)),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> Page[TicketResponse]:
    """List tickets without exposing credentials or hashes."""

    return admin_tickets.list_tickets(
        session,
        event_id=access.event_id,
        page=page,
        page_size=page_size,
        ticket_status=ticket_status,
        reference=reference,
    )


@router.post(
    "/events/{event_slug}/tickets/{ticket_reference}/revoke",
    response_model=TicketResponse,
)
def revoke_ticket(
    event_slug: str,
    ticket_reference: str,
    access: EventAccess = Depends(require_permission_by_slug(Permission.TICKET_MANAGE)),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> TicketResponse:
    """Revoke an active ticket atomically."""

    return admin_tickets.revoke_ticket(
        session,
        event_id=access.event_id,
        ticket_reference=ticket_reference,
        actor_user_id=access.user_id,
    )


@router.post(
    "/events/{event_slug}/tickets/{ticket_reference}/resend",
    response_model=TicketResendResponse,
)
def resend_ticket(
    event_slug: str,
    ticket_reference: str,
    access: EventAccess = Depends(require_permission_by_slug(Permission.TICKET_MANAGE)),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> TicketResendResponse:
    """Queue a ticket-email resend job through the existing outbox."""

    return admin_tickets.resend_ticket(
        session,
        event_id=access.event_id,
        ticket_reference=ticket_reference,
        actor_user_id=access.user_id,
    )


# --- Staff -----------------------------------------------------------------------------


@router.get("/events/{event_slug}/staff", response_model=Page[StaffResponse])
def list_staff(
    event_slug: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    role: StaffRole | None = None,
    access: EventAccess = Depends(require_permission_by_slug(Permission.STAFF_MANAGE)),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> Page[StaffResponse]:
    """List event staff memberships."""

    return admin_staff.list_staff(
        session, event_id=access.event_id, page=page, page_size=page_size, role=role
    )


@router.post("/events/{event_slug}/staff", response_model=StaffResponse, status_code=201)
def add_staff(
    event_slug: str,
    payload: StaffCreateRequest,
    access: EventAccess = Depends(require_permission_by_slug(Permission.STAFF_MANAGE)),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> StaffResponse:
    """Assign an existing Supabase Auth user to this event."""

    return admin_staff.add_staff(
        session,
        event_id=access.event_id,
        user_id=payload.user_id,
        role=payload.role,
        actor_user_id=access.user_id,
    )


@router.patch("/events/{event_slug}/staff/{user_id}", response_model=StaffResponse)
def change_staff_role(
    event_slug: str,
    user_id: UUID,
    payload: StaffRoleUpdate,
    access: EventAccess = Depends(require_permission_by_slug(Permission.STAFF_MANAGE)),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> StaffResponse:
    """Change a staff role while preserving the final event admin."""

    return admin_staff.change_staff_role(
        session,
        event_id=access.event_id,
        user_id=user_id,
        role=payload.role,
        actor_user_id=access.user_id,
    )


@router.delete("/events/{event_slug}/staff/{user_id}", status_code=204)
def remove_staff(
    event_slug: str,
    user_id: UUID,
    access: EventAccess = Depends(require_permission_by_slug(Permission.STAFF_MANAGE)),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Remove a staff membership while preserving the final event admin."""

    admin_staff.remove_staff(
        session,
        event_id=access.event_id,
        user_id=user_id,
        actor_user_id=access.user_id,
    )
    return Response(status_code=204)


# --- Analytics -------------------------------------------------------------------------


@router.get(
    "/events/{event_slug}/analytics/overview",
    response_model=OverviewAnalyticsResponse,
)
def analytics_overview(
    event_slug: str,
    access: EventAccess = Depends(require_permission_by_slug(Permission.EVENT_STATS_VIEW)),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> OverviewAnalyticsResponse:
    """Return aggregate operational counts without attendee PII."""

    return admin_analytics.overview(session, event_id=access.event_id, event_slug=event_slug)


@router.get(
    "/events/{event_slug}/analytics/registrations",
    response_model=RegistrationAnalyticsResponse,
)
def analytics_registrations(
    event_slug: str,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    access: EventAccess = Depends(require_permission_by_slug(Permission.EVENT_STATS_VIEW)),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> RegistrationAnalyticsResponse:
    """Return registration counts over time."""

    return admin_analytics.registrations(
        session,
        event_id=access.event_id,
        from_date=from_date,
        to_date=to_date,
    )


@router.get(
    "/events/{event_slug}/analytics/attendance",
    response_model=AttendanceAnalyticsResponse,
)
def analytics_attendance(
    event_slug: str,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    access: EventAccess = Depends(require_permission_by_slug(Permission.EVENT_STATS_VIEW)),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> AttendanceAnalyticsResponse:
    """Return attendance totals and check-in counts over time."""

    return admin_analytics.attendance(
        session,
        event_id=access.event_id,
        from_date=from_date,
        to_date=to_date,
    )


@router.get(
    "/events/{event_slug}/analytics/email-deliveries",
    response_model=EmailAnalyticsResponse,
)
def analytics_email_deliveries(
    event_slug: str,
    access: EventAccess = Depends(require_permission_by_slug(Permission.EVENT_STATS_VIEW)),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> EmailAnalyticsResponse:
    """Return outbox counts and attempt statistics."""

    return admin_analytics.email_deliveries(session, event_id=access.event_id)


# --- Exports ---------------------------------------------------------------------------


def _enforce_export_limit(request: Request, access: EventAccess) -> None:
    enforce_rate_limit(
        request,
        RateLimitScope.ADMIN_EXPORT,
        build_subject("admin_export", access.event_id, access.user_id),
    )


@router.get("/events/{event_slug}/exports/attendees.csv")
def export_attendees_csv(
    request: Request,
    event_slug: str,
    access: EventAccess = Depends(require_permission_by_slug(Permission.ATTENDANCE_EXPORT)),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Stream the attendee list as CSV."""

    _enforce_export_limit(request, access)
    return admin_exports.export_attendees(
        session,
        event_id=access.event_id,
        event_slug=event_slug,
        export_format=ExportFormat.CSV,
        actor_user_id=access.user_id,
    )


@router.get("/events/{event_slug}/exports/attendees.xlsx")
def export_attendees_xlsx(
    request: Request,
    event_slug: str,
    access: EventAccess = Depends(require_permission_by_slug(Permission.ATTENDANCE_EXPORT)),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Stream the attendee list as XLSX."""

    _enforce_export_limit(request, access)
    return admin_exports.export_attendees(
        session,
        event_id=access.event_id,
        event_slug=event_slug,
        export_format=ExportFormat.XLSX,
        actor_user_id=access.user_id,
    )


@router.get("/events/{event_slug}/exports/checkins.csv")
def export_checkins_csv(
    request: Request,
    event_slug: str,
    access: EventAccess = Depends(require_permission_by_slug(Permission.ATTENDANCE_EXPORT)),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Stream the check-in list as CSV."""

    _enforce_export_limit(request, access)
    return admin_exports.export_checkins(
        session,
        event_id=access.event_id,
        event_slug=event_slug,
        export_format=ExportFormat.CSV,
        actor_user_id=access.user_id,
    )


@router.get("/events/{event_slug}/exports/checkins.xlsx")
def export_checkins_xlsx(
    request: Request,
    event_slug: str,
    access: EventAccess = Depends(require_permission_by_slug(Permission.ATTENDANCE_EXPORT)),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Stream the check-in list as XLSX."""

    _enforce_export_limit(request, access)
    return admin_exports.export_checkins(
        session,
        event_id=access.event_id,
        event_slug=event_slug,
        export_format=ExportFormat.XLSX,
        actor_user_id=access.user_id,
    )


# --- Audit logs ------------------------------------------------------------------------


@router.get("/events/{event_slug}/audit-logs", response_model=Page[AuditLogResponse])
def list_audit_logs(
    event_slug: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    action: str | None = Query(default=None, max_length=100),
    actor_user_id: UUID | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    sort_order: SortOrder = SortOrder.DESC,
    access: EventAccess = Depends(require_permission_by_slug(Permission.AUDIT_VIEW)),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> Page[AuditLogResponse]:
    """Return redacted audit-log entries with filters."""

    return admin_audit.list_audit_logs(
        session,
        event_id=access.event_id,
        page=page,
        page_size=page_size,
        action=action,
        actor_user_id=actor_user_id,
        from_date=from_date,
        to_date=to_date,
        sort_order=sort_order,
    )


# --- Email delivery monitoring ----------------------------------------------------------


@router.get("/events/{event_slug}/email-deliveries", response_model=Page[EmailDeliveryResponse])
def list_email_deliveries(
    event_slug: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    status: EmailDeliveryStatus | None = None,
    registration_reference: str | None = Query(default=None, max_length=64),
    ticket_reference: str | None = Query(default=None, max_length=64),
    min_attempts: int | None = Query(default=None, ge=0, le=20),
    max_attempts: int | None = Query(default=None, ge=0, le=20),
    error_code: str | None = Query(default=None, max_length=64),
    next_attempt_before: datetime | None = None,
    next_attempt_after: datetime | None = None,
    access: EventAccess = Depends(require_permission_by_slug(Permission.EMAIL_DELIVERY_VIEW)),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> Page[EmailDeliveryResponse]:
    """Return outbox jobs with safe status, reference, and attempt filters."""

    return admin_email.list_deliveries(
        session,
        event_id=access.event_id,
        page=page,
        page_size=page_size,
        status=status,
        registration_reference=registration_reference,
        ticket_reference=ticket_reference,
        min_attempts=min_attempts,
        max_attempts=max_attempts,
        error_code=error_code,
        next_attempt_before=next_attempt_before,
        next_attempt_after=next_attempt_after,
    )


@router.post(
    "/events/{event_slug}/email-deliveries/{delivery_reference}/retry",
    response_model=EmailRetryResponse,
)
def retry_email_delivery(
    event_slug: str,
    delivery_reference: UUID,
    access: EventAccess = Depends(require_permission_by_slug(Permission.EMAIL_DELIVERY_MANAGE)),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> EmailRetryResponse:
    """Queue a replacement job for a failed or dead-letter delivery."""

    return admin_email.retry_delivery(
        session,
        event_id=access.event_id,
        delivery_reference=delivery_reference,
        actor_user_id=access.user_id,
    )


# --- Event-scoped eligibility roster ----------------------------------------------------


def _enforce_roster_import_limit(request: Request, access: EventAccess) -> None:
    enforce_rate_limit(
        request,
        RateLimitScope.ADMIN_ROSTER_IMPORT,
        build_subject("admin_roster_import", access.event_id, access.user_id),
    )


@router.get("/events/{event_slug}/eligibility-roster", response_model=Page[RosterEntryResponse])
def list_eligibility_roster(
    event_slug: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    access: EventAccess = Depends(require_permission_by_slug(Permission.EVENT_MANAGE)),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> Page[RosterEntryResponse]:
    """Return the event's normalized eligibility URN roster to administrators only."""

    del event_slug
    return eligibility.list_entries(
        session,
        event_id=access.event_id,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/events/{event_slug}/eligibility-roster/import/dry-run",
    response_model=RosterImportResponse,
)
def dry_run_eligibility_roster_import(
    event_slug: str,
    payload: RosterCsvRequest,
    request: Request,
    access: EventAccess = Depends(require_permission_by_slug(Permission.EVENT_MANAGE)),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> RosterImportResponse:
    """Validate a CSV roster and return counts without writing any records."""

    del event_slug
    _enforce_roster_import_limit(request, access)
    settings: Settings = request.app.state.settings
    return eligibility.preview_import(
        session,
        event_id=access.event_id,
        payload=payload.content_base64,
        filename=payload.filename,
        settings=settings,
    )


@router.post(
    "/events/{event_slug}/eligibility-roster/import",
    response_model=RosterImportResponse,
    status_code=201,
)
def confirm_eligibility_roster_import(
    event_slug: str,
    payload: RosterConfirmRequest,
    request: Request,
    access: EventAccess = Depends(require_permission_by_slug(Permission.EVENT_MANAGE)),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> RosterImportResponse:
    """Import a confirmed CSV roster transactionally for one event."""

    del event_slug
    _enforce_roster_import_limit(request, access)
    settings: Settings = request.app.state.settings
    return eligibility.confirm_import(
        session,
        event_id=access.event_id,
        payload=payload.content_base64,
        filename=payload.filename,
        settings=settings,
        actor_user_id=access.user_id,
    )
