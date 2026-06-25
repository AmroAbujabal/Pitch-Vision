"""
tests/test_db/test_repository.py

TDD tests for database/repository.py.
Uses an in-memory SQLite database — no PostgreSQL required.

Run with: pytest tests/test_db/test_repository.py -v
"""

import pytest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from database.models import Base, Academy, Match, Player, PlayerMatchStats, DevelopmentScore
from database.repository import PipelineResult, PressStatsLike, save_pipeline_results
from metrics.physical import PhysicalMetrics


# ---------------------------------------------------------------------------
# In-memory SQLite fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    """Fresh session per test, rolled back after."""
    with Session(engine) as s:
        yield s
        s.rollback()


@pytest.fixture
def academy(session) -> Academy:
    a = Academy(name="Test Academy", city="Dubai", country="UAE", tier="starter")
    session.add(a)
    session.flush()
    return a


@pytest.fixture
def match(session, academy) -> Match:
    m = Match(
        academy_id=academy.id,
        home_team="Team A",
        away_team="Team B",
        processing_status="processing",
        fps=25.0,
    )
    session.add(m)
    session.flush()
    return m


# ---------------------------------------------------------------------------
# PipelineResult dataclass
# ---------------------------------------------------------------------------

class TestPipelineResult:

    def test_can_be_constructed_with_empty_metrics(self, match):
        result = PipelineResult(
            match_id=match.id,
            fps=25.0,
            physical_metrics={},
            pitch_control_by_track={},
            press_stats={},
            track_teams={},
        )
        assert result.match_id == match.id


# ---------------------------------------------------------------------------
# save_pipeline_results — basic persistence
# ---------------------------------------------------------------------------

class TestSavePipelineResults:

    def _make_physical(self, track_id: int, distance: float = 5000.0) -> PhysicalMetrics:
        return PhysicalMetrics(
            track_id=track_id,
            top_speed_ms=9.2,
            avg_speed_ms=4.5,
            distance_covered_m=distance,
            hi_run_count=8,
            sprint_count=3,
        )

    def _make_press(self, track_id: int) -> PressStatsLike:
        from dataclasses import dataclass

        @dataclass
        class _FakePress:
            press_count: int = 6
            success_count: int = 4
            press_success_rate: float = 4 / 6
            trigger_accuracy: float = 0.5

        return _FakePress()

    def _make_pitch_control(self, track_id: int, contribution: float = 0.62) -> float:
        return contribution

    def test_creates_one_player_stats_row_per_track(self, session, match):
        track_ids = [1, 2, 3]
        result = PipelineResult(
            match_id=match.id,
            fps=25.0,
            physical_metrics={tid: self._make_physical(tid) for tid in track_ids},
            pitch_control_by_track={tid: self._make_pitch_control(tid) for tid in track_ids},
            press_stats={},
            track_teams={tid: "home" for tid in track_ids},
        )
        count = save_pipeline_results(session, match.academy_id, result)
        assert count == 3

        rows = session.execute(
            select(PlayerMatchStats).where(PlayerMatchStats.match_id == match.id)
        ).scalars().all()
        assert len(rows) == 3

    def test_physical_metrics_persisted_correctly(self, session, match):
        track_id = 10
        physical = self._make_physical(track_id, distance=8500.0)
        result = PipelineResult(
            match_id=match.id,
            fps=25.0,
            physical_metrics={track_id: physical},
            pitch_control_by_track={},
            press_stats={},
            track_teams={track_id: "away"},
        )
        save_pipeline_results(session, match.academy_id, result)

        row = session.execute(
            select(PlayerMatchStats).where(PlayerMatchStats.match_id == match.id)
        ).scalar_one()

        assert row.distance_covered_m == pytest.approx(8500.0, rel=0.01)
        assert row.top_speed_ms == pytest.approx(9.2, rel=0.01)
        assert row.avg_speed_ms == pytest.approx(4.5, rel=0.01)
        assert row.hi_run_count == 8
        assert row.sprint_count == 3

    def test_press_stats_persisted_correctly(self, session, match):
        track_id = 20
        press = self._make_press(track_id)
        result = PipelineResult(
            match_id=match.id,
            fps=25.0,
            physical_metrics={track_id: self._make_physical(track_id)},
            pitch_control_by_track={},
            press_stats={track_id: press},
            track_teams={track_id: "home"},
        )
        save_pipeline_results(session, match.academy_id, result)

        row = session.execute(
            select(PlayerMatchStats).where(PlayerMatchStats.match_id == match.id)
        ).scalar_one()

        assert row.press_count == 6
        assert row.press_success_rate == pytest.approx(4 / 6, rel=0.01)

    def test_pitch_control_contribution_persisted(self, session, match):
        track_id = 30
        result = PipelineResult(
            match_id=match.id,
            fps=25.0,
            physical_metrics={track_id: self._make_physical(track_id)},
            pitch_control_by_track={track_id: 0.73},
            press_stats={},
            track_teams={track_id: "home"},
        )
        save_pipeline_results(session, match.academy_id, result)

        row = session.execute(
            select(PlayerMatchStats).where(PlayerMatchStats.match_id == match.id)
        ).scalar_one()

        assert row.pitch_control_contribution == pytest.approx(0.73, rel=0.01)

    def test_track_with_no_press_stats_saves_zero(self, session, match):
        track_id = 40
        result = PipelineResult(
            match_id=match.id,
            fps=25.0,
            physical_metrics={track_id: self._make_physical(track_id)},
            pitch_control_by_track={},
            press_stats={},   # no press stats for this track
            track_teams={track_id: "away"},
        )
        save_pipeline_results(session, match.academy_id, result)

        row = session.execute(
            select(PlayerMatchStats).where(PlayerMatchStats.match_id == match.id)
        ).scalar_one()

        assert row.press_count == 0

    def test_match_processing_status_updated_to_done(self, session, match):
        result = PipelineResult(
            match_id=match.id,
            fps=25.0,
            physical_metrics={1: self._make_physical(1)},
            pitch_control_by_track={},
            press_stats={},
            track_teams={1: "home"},
        )
        save_pipeline_results(session, match.academy_id, result)
        session.refresh(match)
        assert match.processing_status == "done"

    def test_empty_pipeline_result_marks_match_done(self, session, match):
        result = PipelineResult(
            match_id=match.id,
            fps=25.0,
            physical_metrics={},
            pitch_control_by_track={},
            press_stats={},
            track_teams={},
        )
        count = save_pipeline_results(session, match.academy_id, result)
        assert count == 0
        session.refresh(match)
        assert match.processing_status == "done"


# ---------------------------------------------------------------------------
# save_pipeline_results — DevelopmentScore upsert
# ---------------------------------------------------------------------------

class TestDevelopmentScoreUpsert:

    def _run(self, session, match, track_id=1, distance=9000.0, sprint_count=15,
             press_success_rate=0.5, pitch_control=0.075):
        class _FakePress:
            def __init__(self):
                self.press_count = 10
                self.press_success_rate = press_success_rate
                self.trigger_accuracy = 0.6

        result = PipelineResult(
            match_id=match.id,
            fps=25.0,
            physical_metrics={track_id: PhysicalMetrics(
                track_id=track_id,
                top_speed_ms=7.0,
                avg_speed_ms=4.0,
                distance_covered_m=distance,
                hi_run_count=20,
                sprint_count=sprint_count,
            )},
            pitch_control_by_track={track_id: pitch_control},
            press_stats={track_id: _FakePress()},
            track_teams={track_id: "home"},
        )
        save_pipeline_results(session, match.academy_id, result)

    def test_creates_development_score_after_save(self, session, match):
        self._run(session, match)
        scores = session.execute(select(DevelopmentScore)).scalars().all()
        assert len(scores) == 1

    def test_development_score_overall_is_between_zero_and_ten(self, session, match):
        self._run(session, match)
        score = session.execute(select(DevelopmentScore)).scalar_one()
        assert 0.0 <= score.overall_score <= 10.0

    def test_development_score_has_physical_tactical_technical(self, session, match):
        self._run(session, match)
        score = session.execute(select(DevelopmentScore)).scalar_one()
        assert score.physical_score is not None
        assert score.tactical_score is not None
        assert score.technical_score is not None

    def test_week_start_is_monday(self, session, match):
        self._run(session, match)
        score = session.execute(select(DevelopmentScore)).scalar_one()
        assert score.week_start.weekday() == 0  # Monday = 0

    def test_second_match_same_week_upserts_existing_score(self, session, match, academy):
        """Two matches in the same week for the same player → one DevelopmentScore row."""
        # First match
        self._run(session, match, track_id=1)

        # Second match same week
        match2 = Match(
            academy_id=academy.id,
            home_team="X", away_team="Y",
            processing_status="processing", fps=25.0,
        )
        session.add(match2)
        session.flush()
        self._run(session, match2, track_id=1)

        # The player was created by track_id=1 in both → same player record
        player = session.execute(select(Player)).scalar_one()
        scores = session.execute(
            select(DevelopmentScore).where(DevelopmentScore.player_id == player.id)
        ).scalars().all()
        assert len(scores) == 1

    def test_matches_different_weeks_create_separate_scores(self, session, match, academy):
        from datetime import timedelta

        self._run(session, match, track_id=2)

        match2 = Match(
            academy_id=academy.id,
            home_team="A", away_team="B",
            processing_status="processing", fps=25.0,
        )
        session.add(match2)
        session.flush()

        # Force week_start to be next week by patching the function
        from unittest.mock import patch
        from datetime import datetime, timezone
        next_monday = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        # add 7 days to land in a different week
        next_monday = next_monday + timedelta(days=7)
        next_monday = next_monday - timedelta(days=next_monday.weekday())

        with patch("database.repository._week_start", return_value=next_monday):
            self._run(session, match2, track_id=2)

        player = session.execute(
            select(Player).where(Player.name == "Track 2")
        ).scalar_one()
        scores = session.execute(
            select(DevelopmentScore).where(DevelopmentScore.player_id == player.id)
        ).scalars().all()
        assert len(scores) == 2
