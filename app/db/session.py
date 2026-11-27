"""SQLAlchemy engine, session factory, and readiness probe."""

from __future__ import annotations

import logging
from collections.abc import Generator
from typing import Any

from fastapi import Request
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.logging import get_logger, log_event

logger = get_logger(__name__)


def create_db_engine(settings: Settings) -> Engine:
    """Create an engine without opening a connection."""
    url = settings.database_url_value()

    if url.startswith("sqlite+pysqlite://"):
        return create_engine(
            url,
            connect_args={"check_same_thread": False},
            echo=settings.db_echo,
        )

    connect_args: dict[str, Any] = {
        "options": f"-c statement_timeout={settings.db_statement_timeout_ms}"
    }
    if settings.db_prepare_threshold is not None:
        # Supabase transaction pooling does not support named prepared statements.
        connect_args["prepare_threshold"] = settings.db_prepare_threshold
    return create_engine(
        url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_seconds,
        pool_recycle=settings.db_pool_recycle_seconds,
        pool_pre_ping=True,
        connect_args=connect_args,
        echo=settings.db_echo,
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory bound to an engine."""
    return sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
        class_=Session,
    )


def get_session(request: Request) -> Generator[Session, None, None]:
    """FastAPI dependency that yields a scoped database session."""
    factory: sessionmaker[Session] = request.app.state.session_factory
    with factory() as session:
        yield session


def get_db_health(request: Request) -> bool:
    """FastAPI dependency that checks database connectivity."""
    engine: Engine = request.app.state.engine
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        log_event(
            logger,
            logging.WARNING,
            "database_readiness_failed",
            error_type=type(exc).__name__,
        )
        return False
    return True
