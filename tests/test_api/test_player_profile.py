"""
tests/test_api/test_player_profile.py

TDD tests for:
  GET /api/v1/players/{id}/profile
  GET /api/v1/players/{id}/heatmap

Run with: pytest tests/test_api/test_player_profile.py -v
"""

from datetime import datetime, timezone

import pytest

from database.models import Academy, DevelopmentScore, Match, Player, PlayerMatchStats


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def profile_player(db_session, auth_academy):
    """A player with no match stats and no development scores."""
    academy = Academy(name="Profile FC", city="Vancouver", country="Canada", tier="pro")
    db_session.add(academy)
    db_session.flush()
    auth_academy["id"] = academy.id

    player = Player(
        academy_id=academy.id,
        name="Ali Hassan",
        position="CM",
        jersey_number=8,
    )
    db_session.add(player)
    db_session.commit()
    return player


@pytest.fixture
def profile_player_with_stats(db_session, auth_academy):
    """A player with one match and PlayerMatchStats (including heatmap_data)."""
    academy = Academy(name="Stats FC", city="Victoria", country="Canada", tier="pro")
    db_session.add(academy)
    db_session.flush()
    auth_academy["id"] = academy.id

    match = Match(
        academy_id=academy.id,
        home_team="Stats Home",
        away_team="Stats Away",
        processing_status="done",
        fps=25.0,
    )
    db_session.add(match)
    db_session.flush()

    player = Player(
        academy_id=academy.id,
        name="Omar Said",
        position="ST",
        jersey_number=9,
    )
    db_session.add(player)
    db_session.flush()

    stats = PlayerMatchStats(
        player_id=player.id,
        match_id=match.id,
        team="home",
        distance_covered_m=9800.0,
        top_speed_ms=9.8,
        avg_speed_ms=5.5,
        sprint_count=7,
        hi_run_count=18,
        press_count=10,
        press_success_rate=0.70,
        pitch_control_contribution=0.63,
        heatmap_data={"grid": [[0.1, 0.2], [0.3, 0.4]], "rows": 2, "cols": 2},
    )
    db_session.add(stats)
    db_session.commit()

    return {"player": player, "match": match, "stats": stats}


@pytest.fixture
def profile_player_with_dev_scores(db_session, profile_player_with_stats):
    """Extends the stats fixture by adding two weekly development scores."""
    player = profile_player_with_stats["player"]

    score_older = DevelopmentScore(
        player_id=player.id,
        week_start=datetime(2025, 1, 6, tzinfo=timezone.utc),
        overall_score=70.0,
        physical_score=68.0,
        tactical_score=72.0,
        technical_score=70.0,
    )
    score_newer = DevelopmentScore(
        player_id=player.id,
        week_start=datetime(2025, 1, 13, tzinfo=timezone.utc),
        overall_score=74.0,
        physical_score=72.0,
        tactical_score=75.0,
        technical_score=75.0,
    )
    db_session.add_all([score_older, score_newer])
    db_session.commit()

    return {**profile_player_with_stats, "scores": [score_older, score_newer]}


# ---------------------------------------------------------------------------
# GET /api/v1/players/{id}/profile
# ---------------------------------------------------------------------------

class TestPlayerProfile:

    def test_returns_404_for_unknown_player(self, client):
        resp = client.get(
            "/api/v1/players/00000000-0000-0000-0000-000000000000/profile"
        )
        assert resp.status_code == 404

    def test_returns_200_for_existing_player(self, client, profile_player):
        resp = client.get(f"/api/v1/players/{profile_player.id}/profile")
        assert resp.status_code == 200

    def test_response_has_player_bio_fields(self, client, profile_player):
        data = client.get(f"/api/v1/players/{profile_player.id}/profile").json()
        assert data["player_id"] == str(profile_player.id)
        assert data["name"] == "Ali Hassan"
        assert data["position"] == "CM"
        assert data["jersey_number"] == 8

    def test_latest_stats_is_none_when_no_stats(self, client, profile_player):
        data = client.get(f"/api/v1/players/{profile_player.id}/profile").json()
        assert data["latest_stats"] is None

    def test_development_trend_is_empty_when_no_scores(self, client, profile_player):
        data = client.get(f"/api/v1/players/{profile_player.id}/profile").json()
        assert data["development_trend"] == []

    def test_latest_stats_populated_when_stats_exist(
        self, client, profile_player_with_stats
    ):
        player_id = profile_player_with_stats["player"].id
        data = client.get(f"/api/v1/players/{player_id}/profile").json()
        stats = data["latest_stats"]
        assert stats is not None
        assert stats["top_speed_ms"] == pytest.approx(9.8, rel=0.01)
        assert stats["distance_covered_m"] == pytest.approx(9800.0, rel=0.01)
        assert stats["sprint_count"] == 7
        assert stats["press_count"] == 10
        assert stats["pitch_control_contribution"] == pytest.approx(0.63, rel=0.01)

    def test_development_trend_ordered_newest_first(
        self, client, profile_player_with_dev_scores
    ):
        player_id = profile_player_with_dev_scores["player"].id
        data = client.get(f"/api/v1/players/{player_id}/profile").json()
        trend = data["development_trend"]
        assert len(trend) == 2
        # Newest first: week starting Jan 13 before Jan 6
        assert trend[0]["overall_score"] == pytest.approx(74.0, rel=0.01)
        assert trend[1]["overall_score"] == pytest.approx(70.0, rel=0.01)

    def test_development_trend_has_sub_scores(
        self, client, profile_player_with_dev_scores
    ):
        player_id = profile_player_with_dev_scores["player"].id
        data = client.get(f"/api/v1/players/{player_id}/profile").json()
        newest = data["development_trend"][0]
        assert newest["physical_score"] == pytest.approx(72.0, rel=0.01)
        assert newest["tactical_score"] == pytest.approx(75.0, rel=0.01)
        assert newest["technical_score"] == pytest.approx(75.0, rel=0.01)


# ---------------------------------------------------------------------------
# GET /api/v1/players/{id}/heatmap?match_id=...
# ---------------------------------------------------------------------------

class TestPlayerHeatmap:

    def test_returns_404_for_unknown_player(self, client):
        resp = client.get(
            "/api/v1/players/00000000-0000-0000-0000-000000000000/heatmap"
            "?match_id=00000000-0000-0000-0000-000000000001"
        )
        assert resp.status_code == 404

    def test_returns_404_when_no_stats_row_for_match(
        self, client, profile_player_with_stats
    ):
        player_id = profile_player_with_stats["player"].id
        # Use a match_id that has no stats row for this player
        resp = client.get(
            f"/api/v1/players/{player_id}/heatmap"
            "?match_id=00000000-0000-0000-0000-000000000000"
        )
        assert resp.status_code == 404

    def test_returns_200_when_stats_row_exists(
        self, client, profile_player_with_stats
    ):
        player_id = profile_player_with_stats["player"].id
        match_id = profile_player_with_stats["match"].id
        resp = client.get(
            f"/api/v1/players/{player_id}/heatmap?match_id={match_id}"
        )
        assert resp.status_code == 200

    def test_response_has_player_and_match_ids(
        self, client, profile_player_with_stats
    ):
        player_id = profile_player_with_stats["player"].id
        match_id = profile_player_with_stats["match"].id
        data = client.get(
            f"/api/v1/players/{player_id}/heatmap?match_id={match_id}"
        ).json()
        assert data["player_id"] == str(player_id)
        assert data["match_id"] == str(match_id)

    def test_heatmap_data_returned_when_computed(
        self, client, profile_player_with_stats
    ):
        player_id = profile_player_with_stats["player"].id
        match_id = profile_player_with_stats["match"].id
        data = client.get(
            f"/api/v1/players/{player_id}/heatmap?match_id={match_id}"
        ).json()
        assert data["heatmap_data"] == {
            "grid": [[0.1, 0.2], [0.3, 0.4]],
            "rows": 2,
            "cols": 2,
        }

    def test_heatmap_data_is_none_when_not_yet_computed(
        self, client, db_session, auth_academy
    ):
        """A PlayerMatchStats row exists but heatmap_data was never set."""
        academy = Academy(name="NoHeat FC", city="Vancouver", country="Canada", tier="starter")
        db_session.add(academy)
        db_session.flush()
        auth_academy["id"] = academy.id

        match = Match(
            academy_id=academy.id,
            home_team="H",
            away_team="A",
            processing_status="done",
            fps=25.0,
        )
        db_session.add(match)
        db_session.flush()

        player = Player(
            academy_id=academy.id, name="No Heat", position="GK", jersey_number=1
        )
        db_session.add(player)
        db_session.flush()

        db_session.add(
            PlayerMatchStats(
                player_id=player.id,
                match_id=match.id,
                team="home",
                # heatmap_data intentionally omitted
            )
        )
        db_session.commit()

        data = client.get(
            f"/api/v1/players/{player.id}/heatmap?match_id={match.id}"
        ).json()
        assert data["heatmap_data"] is None
