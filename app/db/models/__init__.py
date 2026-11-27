"""Model registration package.

Importing this package registers every mapped class on the shared MetaData,
which is required by Alembic autogenerate and `alembic check`.
"""

from app.db.models.attendee import Attendee
from app.db.models.audit_log import AuditLog
from app.db.models.checkin import Checkin
from app.db.models.eligibility_roster import EligibilityRosterEntry
from app.db.models.email_delivery import EmailDelivery
from app.db.models.event import Event
from app.db.models.registration import Registration
from app.db.models.staff_membership import StaffMembership
from app.db.models.ticket import Ticket
from app.db.models.webhook_event import WebhookEvent

__all__ = [
    "Attendee",
    "AuditLog",
    "Checkin",
    "EmailDelivery",
    "EligibilityRosterEntry",
    "Event",
    "Registration",
    "StaffMembership",
    "Ticket",
    "WebhookEvent",
]
