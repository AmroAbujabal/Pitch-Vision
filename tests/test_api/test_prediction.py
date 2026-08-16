"""
tests/test_api/test_prediction.py

TDD tests for GET /api/v1/players/{id}/prediction.

Run with: pytest tests/test_api/test_prediction.py -v
"""

from __future__ import annotations

import pickle
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

from database.models import Academy, Match, Player, PlayerMatchStats, DevelopmentScore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def player_with_history(db_session, auth_academy):
    """Player with 5 matches of stats + a DevelopmentScore — enough to predict."""
    academy = Academy(name="Predict FC", city="Abu Dhabi", country="UAE", tier="pro")
    db_session.add(academy)
    db_session.flush()
    auth_academy["id"] = academy.id

    player = Player(academy_id=academy.id, name="Test Player", position="MID")
    db_session.add(player)
    db_session.flush()

    for i in range(5):
        days_ago = (5 - i) * 7
        m = Match(
            academy_id=academy.id,
            home_team="A", away_team="B",
            match_date=datetime.now(timezone.utc) - timedelta(days=days_ago),
            processing_status="done", fps=25.0,
        )
        db_session.add(m)
        db_session.flush()

        db_session.add(PlayerMatchStats(
            player_id=player.id, match_id=m.id, team="home",
            distance_covered_m=9000.0 + i * 100,
            sprint_count=15 + i,
            hi_run_count=20,
            top_speed_ms=7.0,
            press_success_rate=0.5,
            pitch_control_contribution=0.08,
            press_trigger_accuracy=0.6,
        ))
        db_session.flush()

    # Dev score for current week
    now = datetime.now(timezone.utc)
    monday = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    db_session.add(DevelopmentScore(
        player_id=player.id, week_start=monday,
        overall_score=7.2, physical_score=7.5,
        tactical_score=6.8, technical_score=7.0,
    ))
    db_session.commit()
    return player


@pytest.fixture
def player_no_history(db_session, auth_academy):
    """Player with no match stats."""
    academy = db_session.query(Academy).first()
    if academy is None:
        academy = Academy(name="Empty FC", city="Dubai", country="UAE", tier="starter")
        db_session.add(academy)
        db_session.flush()
    auth_academy["id"] = academy.id
    player = Player(academy_id=academy.id, name="No History", position="GK")
    db_session.add(player)
    db_session.commit()
    return player


# ---------------------------------------------------------------------------
# GET /api/v1/players/{id}/prediction
# ---------------------------------------------------------------------------

class TestPlayerPrediction:

    def test_returns_404_for_unknown_player(self, client):
        resp = client.get(f"/api/v1/players/{uuid.uuid4()}/prediction")
        assert resp.status_code == 404

    def test_returns_422_when_not_enough_history(self, client, player_no_history):
        resp = client.get(f"/api/v1/players/{player_no_history.id}/prediction")
        assert resp.status_code == 422

    def test_returns_200_for_player_with_history(self, client, player_with_history):
        with patch("api.routers.players._load_model") as mock_model:
            mock_model.return_value.predict.return_value = [7.8]
            resp = client.get(f"/api/v1/players/{player_with_history.id}/prediction")
        assert resp.status_code == 200

    def test_response_has_required_fields(self, client, player_with_history):
        with patch("api.routers.players._load_model") as mock_model:
            mock_model.return_value.predict.return_value = [7.8]
            data = client.get(
                f"/api/v1/players/{player_with_history.id}/prediction"
            ).json()
        assert "predicted_score" in data
        assert "trend" in data
        assert "confidence" in data
        assert "week" in data

    def test_predicted_score_is_between_zero_and_ten(self, client, player_with_history):
        with patch("api.routers.players._load_model") as mock_model:
            mock_model.return_value.predict.return_value = [8.3]
            data = client.get(
                f"/api/v1/players/{player_with_history.id}/prediction"
            ).json()
        assert 0.0 <= data["predicted_score"] <= 10.0

    def test_trend_is_improving_when_predicted_above_current(self, client, player_with_history):
        # current overall_score fixture = 7.2; predict 8.5 → improving
        with patch("api.routers.players._load_model") as mock_model:
            mock_model.return_value.predict.return_value = [8.5]
            data = client.get(
                f"/api/v1/players/{player_with_history.id}/prediction"
            ).json()
        assert data["trend"] == "improving"

    def test_trend_is_declining_when_predicted_below_current(self, client, player_with_history):
        with patch("api.routers.players._load_model") as mock_model:
            mock_model.return_value.predict.return_value = [5.0]
            data = client.get(
                f"/api/v1/players/{player_with_history.id}/prediction"
            ).json()
        assert data["trend"] == "declining"

    def test_trend_is_stable_when_predicted_close_to_current(self, client, player_with_history):
        # current = 7.2, predict 7.3 → within 0.5 threshold → stable
        with patch("api.routers.players._load_model") as mock_model:
            mock_model.return_value.predict.return_value = [7.3]
            data = client.get(
                f"/api/v1/players/{player_with_history.id}/prediction"
            ).json()
        assert data["trend"] == "stable"

    def test_returns_200_using_fallback_when_no_model_file(self, client, player_with_history):
        """If no trained model exists yet, the endpoint uses a mean-based fallback."""
        with patch("api.routers.players._load_model", return_value=None):
            resp = client.get(f"/api/v1/players/{player_with_history.id}/prediction")
        assert resp.status_code == 200

    def test_fallback_response_has_low_confidence(self, client, player_with_history):
        with patch("api.routers.players._load_model", return_value=None):
            data = client.get(
                f"/api/v1/players/{player_with_history.id}/prediction"
            ).json()
        assert data["confidence"] < 0.5


# ---------------------------------------------------------------------------
# _load_model path handling
# ---------------------------------------------------------------------------

class TestLoadModelPathIsNotCallerControlled:
    """`position` is free text set at player creation and the file it names is
    pickle.load-ed, so it must not be able to point outside _MODEL_DIR."""

    def test_letters_still_select_the_per_position_model(self, tmp_path):
        from api.routers import players

        (tmp_path / "prediction_GK.pkl").write_bytes(pickle.dumps({"m": "gk"}))
        players._load_model.cache_clear()
        with patch.object(players, "_MODEL_DIR", tmp_path):
            assert players._load_model("GK") == {"m": "gk"}
        players._load_model.cache_clear()

    def test_traversal_cannot_reach_a_file_outside_the_model_dir(self, tmp_path):
        """
        The escaping form is a leading slash: "/../../x" makes the filename
        "prediction_/../../X.pkl", whose components are prediction_, .., .., X.
        POSIX only walks ".." through directories that exist, so this also needs
        a real "prediction_" directory — built here so the test would actually
        catch the escape rather than pass for the wrong reason.
        """
        from api.routers import players

        model_dir = tmp_path / "models"
        (model_dir / "prediction_").mkdir(parents=True)
        (tmp_path / "PREDICTION_EVIL.pkl").write_bytes(pickle.dumps({"m": "pwned"}))

        players._load_model.cache_clear()
        with patch.object(players, "_MODEL_DIR", model_dir):
            assert players._load_model("/../../prediction_EVIL") is None
        players._load_model.cache_clear()
