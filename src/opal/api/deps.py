"""FastAPI dependencies."""

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from opal.db.base import SessionLocal
from opal.db.models import User


def get_db() -> Generator[Session, None, None]:
    """Get database session dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Type alias for database session dependency
DbSession = Annotated[Session, Depends(get_db)]


def get_current_user_id(
    x_user_id: Annotated[int | None, Header()] = None,
) -> int | None:
    """Get current user ID from request header.

    Note: This is a placeholder for real auth. Currently uses honor system
    via X-User-Id header.
    """
    return x_user_id


# Type alias for user ID dependency
CurrentUserId = Annotated[int | None, Depends(get_current_user_id)]


def get_current_user(
    db: DbSession,
    user_id: CurrentUserId,
) -> User | None:
    """Get current user from database.

    Returns None if no user ID provided or user not found.
    """
    if user_id is None:
        return None
    return db.query(User).filter(User.id == user_id).first()


# Type alias for current user dependency
CurrentUser = Annotated[User | None, Depends(get_current_user)]


def require_user(
    user: CurrentUser,
) -> User:
    """Require a valid user for the request.

    Raises 401 if no user provided.
    """
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User identification required (X-User-Id header)",
        )
    return user


# Type alias for required user dependency
RequiredUser = Annotated[User, Depends(require_user)]


class Pagination:
    """Pagination parameters."""

    def __init__(
        self,
        skip: int = 0,
        limit: int = 100,
    ):
        if limit > 1000:
            limit = 1000
        if skip < 0:
            skip = 0
        self.skip = skip
        self.limit = limit


# Type alias for pagination dependency
PaginationParams = Annotated[Pagination, Depends()]
