"""
tests/test_api/conftest.py

Shared fixtures for API tests.
Uses in-memory SQLite + FastAPI TestClient with DB dependency override.
"""

import uuid
import pytest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from api.main import app
from api.auth import get_current_academy_id
from api.deps import get_db
from database.models import Base, Academy, Match, Player, PlayerMatchStats


# ---------------------------------------------------------------------------
# Engine + session override (module-scoped — one DB per test module)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def db_engine():
    # StaticPool forces every checkout to reuse the SAME underlying SQLite
    # connection, so all sessions see the same in-memory database and the
    # tables created here are visible throughout the test module.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def SessionFactory(db_engine):
    return sessionmaker(bind=db_engine, autocommit=False, autoflush=False)


@pytest.fixture
def db_session(SessionFactory) -> Session:
    """Fresh session per test, rolled back after."""
    session = SessionFactory()
    yield session
    session.rollback()
    session.close()


_DUMMY_ACADEMY_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def auth_academy() -> dict:
    """
    Which academy the fake bearer token belongs to.

    A mutable holder so `seeded` can point it at the academy it creates. Match
    routes are scoped to the caller's academy, so a token for some unrelated
    id would 404 on every seeded record.
    """
    return {"id": _DUMMY_ACADEMY_ID}


@pytest.fixture
def client(SessionFactory, auth_academy) -> TestClient:
    """TestClient with DB and auth dependencies overridden for testing."""
    def override_get_db():
        db = SessionFactory()
        try:
            yield db
        finally:
            db.close()

    def override_auth():
        # Read at request time, so fixture ordering with `seeded` doesn't matter.
        return auth_academy["id"]

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_academy_id] = override_auth
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Seed data helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def seeded(db_session, auth_academy) -> dict:
    """
    Insert a minimal set of records and return their IDs.
    Returns: {academy, match, home_player, away_player, home_stats, away_stats}

    Points the fake token at the academy it creates, so `client` is authorised
    for these records.
    """
    academy = Academy(name="Test FC", city="Dubai", country="UAE", tier="pro")
    db_session.add(academy)
    db_session.flush()
    auth_academy["id"] = academy.id

    match = Match(
        academy_id=academy.id,
        home_team="Al Ain",
        away_team="Al Jazira",
        processing_status="done",
        fps=25.0,
    )
    db_session.add(match)
    db_session.flush()

    home_player = Player(
        academy_id=academy.id,
        name="Track 1",
        position="CM",
        jersey_number=1,
    )
    away_player = Player(
        academy_id=academy.id,
        name="Track 2",
        position="ST",
        jersey_number=2,
    )
    db_session.add_all([home_player, away_player])
    db_session.flush()

    home_stats = PlayerMatchStats(
        player_id=home_player.id,
        match_id=match.id,
        team="home",
        distance_covered_m=9200.0,
        top_speed_ms=9.4,
        avg_speed_ms=5.1,
        sprint_count=5,
        hi_run_count=14,
        press_count=8,
        press_success_rate=0.625,
        pitch_control_contribution=0.58,
    )
    away_stats = PlayerMatchStats(
        player_id=away_player.id,
        match_id=match.id,
        team="away",
        distance_covered_m=7800.0,
        top_speed_ms=8.9,
        avg_speed_ms=4.7,
        sprint_count=3,
        hi_run_count=9,
        press_count=4,
        press_success_rate=0.50,
        pitch_control_contribution=0.42,
    )
    db_session.add_all([home_stats, away_stats])
    db_session.commit()

    return {
        "academy": academy,
        "match": match,
        "home_player": home_player,
        "away_player": away_player,
        "home_stats": home_stats,
        "away_stats": away_stats,
    }
