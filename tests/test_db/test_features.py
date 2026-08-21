"""
tests/test_db/test_features.py

TDD tests for metrics/features.py — feature assembly for the prediction model.

Run with: pytest tests/test_db/test_features.py -v
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.models import Base, Academy, Match, Player, PlayerMatchStats, DevelopmentScore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s
        s.rollback()


@pytest.fixture
def academy(session):
    a = Academy(name="Feature FC", city="Vancouver", country="Canada", tier="pro")
    session.add(a)
    session.flush()
    return a


def _make_match(session, academy, days_ago: int) -> Match:
    m = Match(
        academy_id=academy.id,
        home_team="A", away_team="B",
        match_date=datetime.now(timezone.utc) - timedelta(days=days_ago),
        processing_status="done", fps=25.0,
    )
    session.add(m)
    session.flush()
    return m


def _make_player(session, academy, position: str = "MID") -> Player:
    p = Player(
        academy_id=academy.id,
        name=f"Player {uuid.uuid4().hex[:6]}",
        position=position,
    )
    session.add(p)
    session.flush()
    return p


def _make_stats(session, player, match, **overrides) -> PlayerMatchStats:
    s = PlayerMatchStats(
        player_id=player.id,
        match_id=match.id,
        team="home",
        distance_covered_m=overrides.get("distance_covered_m", 9000.0),
        sprint_count=overrides.get("sprint_count", 15),
        hi_run_count=overrides.get("hi_run_count", 20),
        top_speed_ms=overrides.get("top_speed_ms", 7.0),
        press_success_rate=overrides.get("press_success_rate", 0.5),
        pitch_control_contribution=overrides.get("pitch_control_contribution", 0.08),
        press_trigger_accuracy=overrides.get("press_trigger_accuracy", 0.6),
    )
    session.add(s)
    session.flush()
    return s


def _make_dev_score(session, player, week_offset_days: int = 0, overall: float = 6.0):
    base = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    monday = base - timedelta(days=base.weekday()) - timedelta(days=week_offset_days)
    ds = DevelopmentScore(
        player_id=player.id,
        week_start=monday,
        overall_score=overall,
        physical_score=overall,
        tactical_score=overall,
        technical_score=overall,
    )
    session.add(ds)
    session.flush()
    return ds


# ---------------------------------------------------------------------------
# assemble_player_features
# ---------------------------------------------------------------------------

class TestAssemblePlayerFeatures:

    def test_returns_empty_list_for_player_with_no_stats(self, session, academy):
        from metrics.features import assemble_player_features
        player = _make_player(session, academy)
        rows = assemble_player_features(player.id, session)
        assert rows == []

    def test_returns_one_row_per_match(self, session, academy):
        from metrics.features import assemble_player_features
        player = _make_player(session, academy)
        for days_ago in [21, 14, 7]:
            m = _make_match(session, academy, days_ago)
            _make_stats(session, player, m)
        rows = assemble_player_features(player.id, session)
        assert len(rows) == 3

    def test_rows_ordered_oldest_first(self, session, academy):
        from metrics.features import assemble_player_features
        player = _make_player(session, academy)
        dates = [21, 14, 7]
        for days_ago in dates:
            m = _make_match(session, academy, days_ago)
            _make_stats(session, player, m)
        rows = assemble_player_features(player.id, session)
        match_dates = [r["match_date"] for r in rows]
        assert match_dates == sorted(match_dates)

    def test_row_contains_required_feature_keys(self, session, academy):
        from metrics.features import assemble_player_features
        player = _make_player(session, academy)
        m = _make_match(session, academy, 7)
        _make_stats(session, player, m)
        row = assemble_player_features(player.id, session)[0]
        for key in [
            "match_date", "distance_covered_m", "sprint_count", "hi_run_count",
            "top_speed_ms", "press_success_rate", "pitch_control_contribution",
        ]:
            assert key in row, f"missing key: {key}"

    def test_feature_values_match_stats(self, session, academy):
        from metrics.features import assemble_player_features
        player = _make_player(session, academy)
        m = _make_match(session, academy, 7)
        _make_stats(session, player, m, distance_covered_m=10500.0, sprint_count=22)
        row = assemble_player_features(player.id, session)[0]
        assert row["distance_covered_m"] == pytest.approx(10500.0)
        assert row["sprint_count"] == 22

    def test_limits_to_n_most_recent_matches(self, session, academy):
        from metrics.features import assemble_player_features
        player = _make_player(session, academy)
        for days_ago in [56, 49, 42, 35, 28, 21, 14, 7]:
            m = _make_match(session, academy, days_ago)
            _make_stats(session, player, m)
        rows = assemble_player_features(player.id, session, n_matches=4)
        assert len(rows) == 4

    def test_n_matches_returns_most_recent(self, session, academy):
        from metrics.features import assemble_player_features
        player = _make_player(session, academy)
        for days_ago in [28, 21, 14, 7]:
            m = _make_match(session, academy, days_ago)
            _make_stats(session, player, m, sprint_count=days_ago)
        rows = assemble_player_features(player.id, session, n_matches=2)
        # Most recent 2 = 7 days ago (sprint=7) and 14 days ago (sprint=14)
        sprint_counts = [r["sprint_count"] for r in rows]
        assert set(sprint_counts) == {7, 14}

    def test_none_metrics_returned_as_none(self, session, academy):
        from metrics.features import assemble_player_features
        player = _make_player(session, academy)
        m = _make_match(session, academy, 7)
        s = PlayerMatchStats(
            player_id=player.id, match_id=m.id, team="home",
            distance_covered_m=None, sprint_count=None,
        )
        session.add(s)
        session.flush()
        row = assemble_player_features(player.id, session)[0]
        assert row["distance_covered_m"] is None
        assert row["sprint_count"] is None


# ---------------------------------------------------------------------------
# build_training_dataset
# ---------------------------------------------------------------------------

class TestBuildTrainingDataset:

    def test_returns_empty_arrays_when_no_players(self, session):
        from metrics.features import build_training_dataset
        X, y = build_training_dataset(session)
        assert len(X) == 0
        assert len(y) == 0

    def test_excludes_players_with_fewer_than_two_matches(self, session, academy):
        from metrics.features import build_training_dataset
        player = _make_player(session, academy)
        m = _make_match(session, academy, 7)
        _make_stats(session, player, m)
        _make_dev_score(session, player, week_offset_days=0)
        X, y = build_training_dataset(session)
        assert len(X) == 0

    def test_produces_one_row_per_valid_transition(self, session, academy):
        from metrics.features import build_training_dataset
        player = _make_player(session, academy)
        for days_ago in [14, 7]:
            m = _make_match(session, academy, days_ago)
            _make_stats(session, player, m)
        # Need a dev score for the target week
        _make_dev_score(session, player, week_offset_days=0, overall=7.5)
        X, y = build_training_dataset(session)
        assert len(X) == 1
        assert y[0] == pytest.approx(7.5, abs=0.01)

    def test_feature_vector_has_correct_length(self, session, academy):
        from metrics.features import build_training_dataset, FEATURE_KEYS
        player = _make_player(session, academy)
        for days_ago in [14, 7]:
            m = _make_match(session, academy, days_ago)
            _make_stats(session, player, m)
        _make_dev_score(session, player, week_offset_days=0, overall=7.0)
        X, y = build_training_dataset(session)
        assert len(X[0]) == len(FEATURE_KEYS)
