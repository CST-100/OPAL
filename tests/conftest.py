"""Pytest configuration and fixtures."""

import os
from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Set test environment before importing app
os.environ["OPAL_DATABASE_URL"] = "sqlite:///:memory:"
os.environ["OPAL_DEBUG"] = "false"

from opal.api.app import create_app
from opal.api.deps import get_db
from opal.db.base import Base
from opal.db.models import User


@pytest.fixture(scope="session")
def engine():
    """Create test database engine."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    return engine


@pytest.fixture(scope="session")
def tables(engine):
    """Create all database tables."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session(engine, tables) -> Generator[Session, None, None]:
    """Create a new database session for each test."""
    connection = engine.connect()
    transaction = connection.begin()

    SessionLocal = sessionmaker(bind=connection)
    session = SessionLocal()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """Create test client with overridden database dependency."""
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def test_user(db_session: Session) -> User:
    """Create a test user."""
    user = User(name="Test User", email="test@example.com")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(test_user: User) -> dict[str, Any]:
    """Create authentication headers with test user."""
    return {"X-User-Id": str(test_user.id)}
