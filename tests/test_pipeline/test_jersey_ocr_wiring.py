"""
tests/test_pipeline/test_jersey_ocr_wiring.py

TDD tests for jersey OCR wiring:
  - PipelineResult.jersey_numbers field
  - save_pipeline_results() uses OCR jersey number over track_id placeholder
  - OCR result applied to player record in DB

Run with: pytest tests/test_pipeline/test_jersey_ocr_wiring.py -v
"""

import pytest
import numpy as np

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from database.models import Base, Academy, Match, Player
from database.repository import PipelineResult, save_pipeline_results
from metrics.physical import PhysicalMetrics
from tracking.types import Track


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s
        s.rollback()


@pytest.fixture
def academy(session):
    a = Academy(name="OCR FC", city="Dubai", country="UAE", tier="pro")
    session.add(a)
    session.flush()
    return a


@pytest.fixture
def match(session, academy):
    m = Match(
        academy_id=academy.id,
        home_team="Home",
        away_team="Away",
        processing_status="processing",
        fps=25.0,
    )
    session.add(m)
    session.flush()
    return m


def _physical(track_id: int) -> PhysicalMetrics:
    return PhysicalMetrics(
        track_id=track_id,
        top_speed_ms=8.0,
        avg_speed_ms=4.0,
        distance_covered_m=6000.0,
        hi_run_count=5,
        sprint_count=2,
    )


def _result(match, track_id: int, jersey_numbers: dict = None) -> PipelineResult:
    return PipelineResult(
        match_id=match.id,
        fps=25.0,
        physical_metrics={track_id: _physical(track_id)},
        pitch_control_by_track={},
        press_stats={},
        track_teams={track_id: "home"},
        jersey_numbers=jersey_numbers or {},
    )


# ---------------------------------------------------------------------------
# Track.best_crop field
# ---------------------------------------------------------------------------

class TestTrackBestCrop:

    def test_track_has_best_crop_field(self):
        t = Track(track_id=1, bbox=np.array([0, 0, 50, 100]))
        assert hasattr(t, "best_crop")

    def test_best_crop_defaults_to_none(self):
        t = Track(track_id=1, bbox=np.array([0, 0, 50, 100]))
        assert t.best_crop is None

    def test_best_crop_accepts_numpy_array(self):
        crop = np.zeros((64, 32, 3), dtype=np.uint8)
        t = Track(track_id=1, bbox=np.array([0, 0, 50, 100]), best_crop=crop)
        assert t.best_crop is crop


# ---------------------------------------------------------------------------
# PipelineResult.jersey_numbers field
# ---------------------------------------------------------------------------

class TestPipelineResultJerseyNumbers:

    def test_jersey_numbers_defaults_to_empty_dict(self, match):
        result = PipelineResult(
            match_id=match.id,
            fps=25.0,
            physical_metrics={},
            pitch_control_by_track={},
            press_stats={},
            track_teams={},
        )
        assert result.jersey_numbers == {}

    def test_jersey_numbers_accepts_track_to_number_mapping(self, match):
        result = _result(match, track_id=7, jersey_numbers={7: 9})
        assert result.jersey_numbers == {7: 9}


# ---------------------------------------------------------------------------
# save_pipeline_results — jersey number application
# ---------------------------------------------------------------------------

class TestJerseyNumberPersistence:

    def test_player_jersey_number_set_from_ocr_when_provided(
        self, session, match, academy
    ):
        """When OCR detects jersey #9 for track 7, player.jersey_number = 9."""
        save_pipeline_results(
            session, academy.id, _result(match, track_id=7, jersey_numbers={7: 9})
        )
        player = session.execute(
            select(Player).where(
                Player.academy_id == academy.id,
                Player.name == "Track 7",
            )
        ).scalar_one()
        assert player.jersey_number == 9

    def test_player_name_still_uses_track_id_without_ocr(
        self, session, match, academy
    ):
        """No jersey_numbers → player name stays 'Track N'."""
        save_pipeline_results(
            session, academy.id, _result(match, track_id=42, jersey_numbers={})
        )
        player = session.execute(
            select(Player).where(
                Player.academy_id == academy.id,
                Player.name == "Track 42",
            )
        ).scalar_one()
        assert player is not None

    def test_two_tracks_with_different_ocr_numbers(self, session, match, academy):
        result = PipelineResult(
            match_id=match.id,
            fps=25.0,
            physical_metrics={10: _physical(10), 11: _physical(11)},
            pitch_control_by_track={},
            press_stats={},
            track_teams={10: "home", 11: "away"},
            jersey_numbers={10: 7, 11: 22},
        )
        save_pipeline_results(session, academy.id, result)

        p10 = session.execute(
            select(Player).where(Player.academy_id == academy.id, Player.name == "Track 10")
        ).scalar_one()
        p11 = session.execute(
            select(Player).where(Player.academy_id == academy.id, Player.name == "Track 11")
        ).scalar_one()

        assert p10.jersey_number == 7
        assert p11.jersey_number == 22

    def test_ocr_number_missing_for_track_doesnt_affect_other_tracks(
        self, session, match, academy
    ):
        """Track 20 has OCR, track 21 doesn't — both save correctly."""
        result = PipelineResult(
            match_id=match.id,
            fps=25.0,
            physical_metrics={20: _physical(20), 21: _physical(21)},
            pitch_control_by_track={},
            press_stats={},
            track_teams={20: "home", 21: "home"},
            jersey_numbers={20: 5},  # only track 20 has OCR
        )
        save_pipeline_results(session, academy.id, result)

        p20 = session.execute(
            select(Player).where(Player.academy_id == academy.id, Player.name == "Track 20")
        ).scalar_one()
        p21 = session.execute(
            select(Player).where(Player.academy_id == academy.id, Player.name == "Track 21")
        ).scalar_one()

        assert p20.jersey_number == 5
        assert p21.jersey_number == 21  # falls back to track_id
