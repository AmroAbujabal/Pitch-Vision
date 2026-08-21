"""
tests/test_api/test_auth.py

TDD tests for JWT authentication:
  POST /api/v1/auth/token    — obtain a token
  Protected endpoints        — reject missing/invalid tokens

Run with: pytest tests/test_api/test_auth.py -v
"""

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.deps import get_db
from database.models import Academy


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def enforcing_client(SessionFactory):
    """TestClient with real auth enforcement (no auth override)."""
    def override_get_db():
        db = SessionFactory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    # Deliberately do NOT override get_current_academy_id
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def academy_with_password(db_session):
    """An academy with a hashed password stored in the DB."""
    from api.auth import hash_password

    academy = Academy(
        name="Auth FC",
        city="Vancouver",
        country="Canada",
        tier="pro",
        password_hash=hash_password("secret123"),
    )
    db_session.add(academy)
    db_session.commit()
    return academy


# ---------------------------------------------------------------------------
# POST /api/v1/auth/token
# ---------------------------------------------------------------------------

class TestObtainToken:

    def test_returns_200_with_valid_credentials(
        self, enforcing_client, academy_with_password
    ):
        resp = enforcing_client.post(
            "/api/v1/auth/token",
            data={
                "username": str(academy_with_password.id),
                "password": "secret123",
            },
        )
        assert resp.status_code == 200

    def test_response_has_access_token_and_type(
        self, enforcing_client, academy_with_password
    ):
        data = enforcing_client.post(
            "/api/v1/auth/token",
            data={
                "username": str(academy_with_password.id),
                "password": "secret123",
            },
        ).json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_returns_401_for_wrong_password(
        self, enforcing_client, academy_with_password
    ):
        resp = enforcing_client.post(
            "/api/v1/auth/token",
            data={
                "username": str(academy_with_password.id),
                "password": "wrongpassword",
            },
        )
        assert resp.status_code == 401

    def test_returns_401_for_unknown_academy_id(self, enforcing_client):
        resp = enforcing_client.post(
            "/api/v1/auth/token",
            data={
                "username": "00000000-0000-0000-0000-000000000000",
                "password": "anything",
            },
        )
        assert resp.status_code == 401

    def test_returns_422_when_credentials_missing(self, enforcing_client):
        resp = enforcing_client.post("/api/v1/auth/token", data={})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Protected endpoints — token required
# ---------------------------------------------------------------------------

class TestProtectedEndpoints:

    def test_matches_list_rejects_missing_token(self, enforcing_client, seeded):
        resp = enforcing_client.get(
            f"/api/v1/matches/?academy_id={seeded['academy'].id}",
        )
        assert resp.status_code == 401

    def test_matches_list_rejects_invalid_token(self, enforcing_client, seeded):
        resp = enforcing_client.get(
            f"/api/v1/matches/?academy_id={seeded['academy'].id}",
            headers={"Authorization": "Bearer notavalidtoken"},
        )
        assert resp.status_code == 401

    def test_matches_list_accepts_valid_token(
        self, enforcing_client, seeded, academy_with_password, db_session
    ):
        from api.auth import hash_password
        seeded["academy"].password_hash = hash_password("pw")
        db_session.commit()

        token = enforcing_client.post(
            "/api/v1/auth/token",
            data={
                "username": str(seeded["academy"].id),
                "password": "pw",
            },
        ).json()["access_token"]

        resp = enforcing_client.get(
            f"/api/v1/matches/?academy_id={seeded['academy'].id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    def test_player_stats_rejects_missing_token(self, enforcing_client, seeded):
        player_id = seeded["home_player"].id
        resp = enforcing_client.get(f"/api/v1/players/{player_id}/stats")
        assert resp.status_code == 401
