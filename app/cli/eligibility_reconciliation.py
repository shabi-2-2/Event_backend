"""CLI for one-time historical Google Forms response reconciliation."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger, log_event
from app.db.session import create_db_engine, create_session_factory
from app.services import eligibility_reconciliation as reconciliation

logger = get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="event-eligibility-reconcile",
        description="Reconcile historical Google Forms responses against one event roster.",
    )
    parser.add_argument("--input", required=True, type=Path, help="JSONL response file")
    parser.add_argument(
        "--event-slug",
        required=True,
        help="Explicit event slug for every historical response",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Process and roll back all changes")
    mode.add_argument("--confirm", action="store_true", help="Process and commit changes")
    return parser


def _run_dry_run(
    settings: Settings,
    input_path: Path,
    event_slug: str,
) -> reconciliation.ReconciliationSummary:
    engine = create_db_engine(settings)
    try:
        with engine.connect() as connection:
            outer = connection.begin()
            try:
                # Resolve the event in a separate session so the processing
                # session is still unbegun and can own each savepoint transaction
                # created by process_rsvp. The outer transaction is never
                # committed, so every write is discarded.
                with Session(
                    bind=connection,
                    join_transaction_mode="create_savepoint",
                ) as lookup_session:
                    reconciliation.resolve_event_id(lookup_session, event_slug)

                requests, invalid = reconciliation.load_historical_requests(input_path, event_slug)
                with Session(
                    bind=connection,
                    autoflush=False,
                    expire_on_commit=False,
                    join_transaction_mode="create_savepoint",
                ) as session:
                    summary = reconciliation.reconcile_records(
                        session,
                        requests=requests,
                        derivation_key=settings.ticket_token_derivation_key_value(),
                        invalid_records=invalid,
                    )
            finally:
                outer.rollback()
    finally:
        engine.dispose()
    return summary


def _run_confirmed(
    settings: Settings,
    input_path: Path,
    event_slug: str,
) -> reconciliation.ReconciliationSummary:
    engine = create_db_engine(settings)
    factory = create_session_factory(engine)
    try:
        with factory() as session:
            reconciliation.resolve_event_id(session, event_slug)
        requests, invalid = reconciliation.load_historical_requests(input_path, event_slug)
        with factory() as session:
            return reconciliation.reconcile_records(
                session,
                requests=requests,
                derivation_key=settings.ticket_token_derivation_key_value(),
                invalid_records=invalid,
            )
    finally:
        engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.input.is_file():
        parser.error("input file does not exist")

    settings = get_settings()
    configure_logging(settings)
    log_event(
        logger,
        logging.INFO,
        "historical_reconciliation_started",
        event_slug=args.event_slug,
        mode="dry_run" if args.dry_run else "confirmed",
    )

    summary = (
        _run_dry_run(settings, args.input, args.event_slug)
        if args.dry_run
        else _run_confirmed(settings, args.input, args.event_slug)
    )
    print(json.dumps(summary.to_dict(), sort_keys=True))
    log_event(logger, logging.INFO, "historical_reconciliation_completed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
