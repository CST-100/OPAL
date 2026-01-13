"""Database session management."""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy.orm import Session

from opal.db.base import SessionLocal


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Context manager for database sessions.

    Usage:
        with get_session() as db:
            db.query(User).all()
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
