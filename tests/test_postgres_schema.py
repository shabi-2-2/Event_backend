"""PostgreSQL-specific schema, constraint, and migration verification.

Run with EVENT_TEST_POSTGRES_URL pointing to an isolated test database and
EVENT_DATABASE_URL set to the same URL. Otherwise these tests skip.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Attendee, Event, WebhookEvent
from app.db.models.common import WebhookOutcome

pytestmark = pytest.mark.postgres

_EXPECTED_ENUMS = {
    "event_status",
    "registration_status",
    "ticket_status",
    "checkin_source",
    "email_purpose",
    "email_delivery_status",
    "webhook_outcome",
    "staff_role",
}


def _make_event() -> Event:
    return Event(
        slug=f"pg-event-{uuid4().hex[:10]}",
        name="PostgreSQL Event",
        starts_at=datetime(2026, 7, 1, 9, tzinfo=UTC),
        ends_at=datetime(2026, 7, 1, 18, tzinfo=UTC),
        timezone="UTC",
    )


def _make_attendee(*, email: str, urn: str | None) -> Attendee:
    return Attendee(
        full_name="PostgreSQL Attendee",
        email=email,
        urn=urn,
    )


def _make_webhook(*, submission_id: str, request_id: str | None) -> WebhookEvent:
    return WebhookEvent(
        source="google_forms",
        event_slug="pg-event-slug",
        submission_id=submission_id,
        request_id=request_id,
        payload_hash="d" * 64,
        outcome=WebhookOutcome.REGISTERED,
    )


def _expect_integrity_error(session: Session) -> None:
    """Assert a constraint failure and roll it back without losing the test transaction."""
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_migration_revision_is_applied(migrated_postgres: Engine) -> None:
    with migrated_postgres.connect() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert revision == "20261127_0004"


def test_native_enums_and_jsonb_columns_exist(migrated_postgres: Engine) -> None:
    with migrated_postgres.connect() as connection:
        enum_types = {
            row[0]
            for row in connection.execute(
                text(
                    "SELECT typname FROM pg_type "
                    "WHERE typtype = 'e' AND typname IN ("
                    "'event_status','registration_status','ticket_status',"
                    "'checkin_source','email_purpose','email_delivery_status',"
                    "'webhook_outcome','staff_role')"
                )
            )
        }
        event_status_type = connection.execute(
            text(
                "SELECT format_type(a.atttypid, a.atttypmod) "
                "FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid "
                "WHERE c.relname = 'events' AND a.attname = 'status'"
            )
        ).scalar_one()
        jsonb_columns = dict(
            connection.execute(
                text(
                    "SELECT table_name, column_name "
                    "FROM information_schema.columns "
                    "WHERE data_type = 'jsonb' "
                    "AND ((table_name = 'checkins' AND column_name = 'metadata') "
                    "OR (table_name = 'audit_logs' AND column_name = 'context'))"
                )
            ).all()
        )

    assert enum_types == _EXPECTED_ENUMS
    assert event_status_type == "event_status"
    assert jsonb_columns == {"checkins": "metadata", "audit_logs": "context"}


def test_all_foreign_keys_use_restrict(migrated_postgres: Engine) -> None:
    with migrated_postgres.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT tc.table_name, rc.delete_rule "
                "FROM information_schema.table_constraints tc "
                "JOIN information_schema.referential_constraints rc "
                "ON tc.constraint_name = rc.constraint_name "
                "AND tc.constraint_schema = rc.constraint_schema "
                "WHERE tc.constraint_type = 'FOREIGN KEY' "
                "AND tc.table_schema = 'public'"
            )
        ).all()

    assert rows
    assert all(row.delete_rule == "RESTRICT" for row in rows)


def test_functional_unique_indexes_on_postgres(pg_session: Session) -> None:
    pg_session.add_all(
        [
            _make_attendee(email="Pg.User@Example.com", urn=" pg-urn-1 "),
            _make_attendee(email="other@example.com", urn="PG-URN-1"),
        ]
    )
    _expect_integrity_error(pg_session)

    pg_session.add_all(
        [
            _make_attendee(email="pg-email-2@example.com", urn="PG-URN-2"),
            _make_attendee(email="PG-EMAIL-2@example.com", urn="PG-URN-3"),
        ]
    )
    _expect_integrity_error(pg_session)

    pg_session.add_all(
        [
            _make_attendee(email=f"external-{uuid4().hex}@example.com", urn=None),
            _make_attendee(email=f"external-{uuid4().hex}@example.com", urn=None),
        ]
    )
    pg_session.flush()


def test_partial_request_id_uniqueness_on_postgres(pg_session: Session) -> None:
    pg_session.add(_make_webhook(submission_id="pg-sub-1", request_id="pg-req-1"))
    pg_session.flush()

    pg_session.add(_make_webhook(submission_id="pg-sub-2", request_id="pg-req-1"))
    _expect_integrity_error(pg_session)

    pg_session.add_all(
        [
            _make_webhook(submission_id="pg-sub-3", request_id=None),
            _make_webhook(submission_id="pg-sub-4", request_id=None),
        ]
    )
    pg_session.flush()


def test_postgres_timestamps_are_timezone_aware(pg_session: Session) -> None:
    event = _make_event()
    pg_session.add(event)
    pg_session.flush()

    assert event.created_at.tzinfo is not None
    assert event.updated_at.tzinfo is not None
