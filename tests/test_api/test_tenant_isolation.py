"""
tests/test_api/test_tenant_isolation.py

Every match and player route must be scoped to the calling academy. These tests
hold that line: a record owned by another academy is invisible, not merely
unwritable.

Run with: pytest tests/test_api/test_tenant_isolation.py -v
"""

import io

import pytest

from database.models import Academy, Match, Player, PlayerMatchStats


CORNERS = [[100.0, 400.0], [1820.0, 400.0], [1900.0, 1000.0], [20.0, 1000.0]]


@pytest.fixture
def foreign_match(db_session, seeded) -> Match:
    """
    A match belonging to a different academy than the caller's token.

    Depends on `seeded` so the token is already pointed at the caller's own
    academy before this rival record is created.
    """
    rival = Academy(name="Rival FC", city="Halifax", country="Canada", tier="pro")
    db_session.add(rival)
    db_session.flush()

    match = Match(
        academy_id=rival.id,
        home_team="Rival Home",
        away_team="Rival Away",
        processing_status="done",
        fps=25.0,
    )
    db_session.add(match)
    db_session.commit()
    return match


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

class TestForeignMatchIsInvisible:

    @pytest.mark.parametrize("path", ["summary", "players", "processing-status"])
    def test_read_returns_404(self, client, foreign_match, path):
        resp = client.get(f"/api/v1/matches/{foreign_match.id}/{path}")
        assert resp.status_code == 404

    def test_404_not_403(self, client, foreign_match):
        """403 would confirm the id exists, letting a caller enumerate matches."""
        resp = client.get(f"/api/v1/matches/{foreign_match.id}/summary")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_listing_excludes_other_academies(self, client, seeded, foreign_match):
        ids = [r["id"] for r in client.get("/api/v1/matches/").json()]
        assert str(seeded["match"].id) in ids
        assert str(foreign_match.id) not in ids


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

class TestForeignMatchIsUnwritable:

    def test_calibration_returns_404(self, client, foreign_match):
        resp = client.put(
            f"/api/v1/matches/{foreign_match.id}/calibration",
            json={"pitch_corners": CORNERS, "home_defends_end": "low"},
        )
        assert resp.status_code == 404

    def test_calibration_leaves_the_record_untouched(
        self, client, foreign_match, db_session
    ):
        client.put(
            f"/api/v1/matches/{foreign_match.id}/calibration",
            json={"pitch_corners": CORNERS, "home_defends_end": "high"},
        )
        db_session.expire_all()
        match = db_session.get(Match, foreign_match.id)
        assert match.pitch_corners is None
        assert match.home_defends_end is None

    def test_upload_returns_404(self, client, foreign_match):
        resp = client.post(
            f"/api/v1/matches/{foreign_match.id}/upload-video",
            files={"file": ("match.mp4", io.BytesIO(b"bytes"), "video/mp4")},
        )
        assert resp.status_code == 404

    def test_reprocess_returns_404(self, client, foreign_match):
        resp = client.post(f"/api/v1/matches/{foreign_match.id}/reprocess")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------

class TestCreateIsOwnedByTheCaller:

    def test_match_belongs_to_the_token_academy(self, client, seeded):
        resp = client.post(
            "/api/v1/matches/",
            json={"home_team": "New Home", "away_team": "New Away"},
        )
        assert resp.status_code == 201
        assert resp.json()["academy_id"] == str(seeded["academy"].id)

    def test_body_academy_id_cannot_reassign_ownership(self, client, seeded):
        """A caller supplying someone else's academy_id must not plant a match
        in their account."""
        resp = client.post(
            "/api/v1/matches/",
            json={
                "home_team": "Planted",
                "away_team": "Match",
                "academy_id": "00000000-0000-0000-0000-000000000000",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["academy_id"] == str(seeded["academy"].id)


# ---------------------------------------------------------------------------
# Players — same rules
# ---------------------------------------------------------------------------

@pytest.fixture
def foreign_player(db_session, foreign_match) -> Player:
    """A player of the rival academy, with one match's stats to read."""
    player = Player(
        academy_id=foreign_match.academy_id,
        name="Rival Winger",
        position="LW",
        jersey_number=11,
    )
    db_session.add(player)
    db_session.flush()

    db_session.add(
        PlayerMatchStats(
            player_id=player.id,
            match_id=foreign_match.id,
            team="home",
            distance_covered_m=8800.0,
            top_speed_ms=9.1,
            heatmap_data={"grid": [[1]]},
        )
    )
    db_session.commit()
    return player


class TestForeignPlayerIsInvisible:

    @pytest.mark.parametrize("path", ["stats", "profile", "prediction"])
    def test_read_returns_404(self, client, foreign_player, path):
        resp = client.get(f"/api/v1/players/{foreign_player.id}/{path}")
        assert resp.status_code == 404

    def test_heatmap_returns_404(self, client, foreign_player, foreign_match):
        resp = client.get(
            f"/api/v1/players/{foreign_player.id}/heatmap?match_id={foreign_match.id}"
        )
        assert resp.status_code == 404

    def test_404_not_403(self, client, foreign_player):
        """403 would confirm the id exists, letting a caller enumerate players."""
        resp = client.get(f"/api/v1/players/{foreign_player.id}/profile")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


class TestCreatePlayerIsOwnedByTheCaller:

    _PLAYER = {"name": "New Signing", "position": "CB"}

    def test_player_belongs_to_the_token_academy(self, client, seeded):
        resp = client.post("/api/v1/players/", json=self._PLAYER)
        assert resp.status_code == 201
        assert resp.json()["academy_id"] == str(seeded["academy"].id)

    def test_body_academy_id_cannot_reassign_ownership(self, client, seeded):
        resp = client.post(
            "/api/v1/players/",
            json={
                **self._PLAYER,
                "academy_id": "00000000-0000-0000-0000-000000000000",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["academy_id"] == str(seeded["academy"].id)
