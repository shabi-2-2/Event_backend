"""Declarative base for future SQLAlchemy models."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all mapped database entities."""
