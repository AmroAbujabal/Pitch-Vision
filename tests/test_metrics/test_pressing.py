"""
tests/test_metrics/test_pressing.py

TDD tests for metrics/pressing.py.
No torch required — imports Track/TrackedFrame from tracking.types.

Run with: pytest tests/test_metrics/test_pressing.py -v
"""

import numpy as np
import pytest

from tracking.types import Track, TrackedFrame
from metrics.pressing import PressAnalyser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_track(
    track_id: int,
    bbox: list,
    team: str,
    *,
    bbox_history: list | None = None,
    pitch_pos: tuple | None = None,
) -> Track:
    t = Track(track_id=track_id, bbox=np.array(bbox, dtype=float), team=team)
    t.is_confirmed = True
    if bbox_history is not None:
        t.bbox_history = [np.array(b, dtype=float) for b in bbox_history]
    if pitch_pos is not None:
        t.pitch_pos = np.array(pitch_pos, dtype=float)
    return t


def make_frame(frame_id: int, tracks: list) -> TrackedFrame:
    return TrackedFrame(frame_id=frame_id, tracks=tracks)


# ---------------------------------------------------------------------------
# Bug fix: the chained assignment `closing = self._closing_speed = ...`
# was removed; tests verify that detect_press_events is robust in edge cases
# that previously caused AttributeError.
# ---------------------------------------------------------------------------

class TestClosingSpeedBug:

    def test_detect_events_on_empty_frame_list_does_not_raise(self):
        result = PressAnalyser().detect_press_events([])
        assert result == []

    def test_detect_events_zero_velocity_tracks_do_not_raise(self):
        """Tracks far apart at zero velocity → no press, no error."""
        home = make_track(1, [0, 0, 0, 0], "home")
        away = make_track(2, [0, 0, 0, 0], "away")
        result = PressAnalyser().detect_press_events([make_frame(0, [home, away])])
        assert isinstance(result, list)

    def test_single_frame_track_no_velocity_no_error(self):
        """Track with only 1 bbox_history entry (velocity=None) must not raise."""
        home = make_track(
            1, [900, 490, 950, 560], "home",
            bbox_history=[[900, 490, 950, 560]],
            pitch_pos=(52.0, 34.0),
        )
        away = make_track(2, [940, 490, 990, 560], "away", pitch_pos=(55.0, 34.0))
        result = PressAnalyser().detect_press_events([make_frame(0, [home, away])])
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Press detection correctness
# ---------------------------------------------------------------------------

class TestPressDetection:

    def test_no_press_when_teams_far_apart(self):
        home = make_track(1, [0, 0, 50, 50], "home", pitch_pos=(5.0, 5.0))
        away = make_track(2, [1800, 1000, 1900, 1100], "away", pitch_pos=(100.0, 60.0))
        assert PressAnalyser().detect_press_events([make_frame(0, [home, away])]) == []

    def test_press_detected_when_close_and_moving_toward_target(self):
        """home at (50,34), away at (53,34) → 3 m apart; home velocity ~13 m/s rightward."""
        home = make_track(
            1, [304, 215, 354, 265], "home",
            bbox_history=[[294, 215, 344, 265], [304, 215, 354, 265]],
            pitch_pos=(50.0, 34.0),
        )
        away = make_track(2, [323, 215, 373, 265], "away", pitch_pos=(53.0, 34.0))
        events = PressAnalyser().detect_press_events([make_frame(0, [home, away])])
        assert len(events) >= 1
        assert events[0].track_id == 1
        assert events[0].target_track_id == 2
        assert events[0].distance_at_start == pytest.approx(3.0, abs=0.1)

    def test_aggregate_player_stats_counts_press(self):
        home = make_track(
            1, [304, 215, 354, 265], "home",
            bbox_history=[[294, 215, 344, 265], [304, 215, 354, 265]],
            pitch_pos=(50.0, 34.0),
        )
        away = make_track(2, [323, 215, 373, 265], "away", pitch_pos=(53.0, 34.0))
        a = PressAnalyser()
        a.detect_press_events([make_frame(0, [home, away])])
        stats = a.aggregate_player_stats()
        assert 1 in stats
        assert stats[1].press_count >= 1


# ---------------------------------------------------------------------------
# Homography wiring in _get_pitch_pos
# Fixtures identity_homography / skewed_homography come from conftest.py.
# ---------------------------------------------------------------------------

class TestPressHomographyWiring:

    def test_analyser_accepts_homography_kwarg(self, identity_homography):
        assert PressAnalyser(homography=identity_homography) is not None

    def test_get_pitch_pos_uses_homography(self, skewed_homography):
        """Non-identity homography gives different position than naive linear."""
        track = make_track(1, [960, 540, 1000, 590], "home")
        pos_with_h = PressAnalyser(homography=skewed_homography)._get_pitch_pos(track)
        pos_without = PressAnalyser()._get_pitch_pos(track)
        assert pos_with_h is not None
        assert not np.allclose(pos_with_h, pos_without, atol=0.5)

    def test_get_pitch_pos_prefers_explicit_pitch_pos(self, skewed_homography):
        """track.pitch_pos takes precedence — homography is not consulted."""
        track = make_track(1, [960, 540, 1000, 590], "home", pitch_pos=(30.0, 20.0))
        pos = PressAnalyser(homography=skewed_homography)._get_pitch_pos(track)
        np.testing.assert_array_equal(pos, [30.0, 20.0])

    def test_detect_events_with_homography_does_not_raise(self, identity_homography):
        home = make_track(
            1, [304, 215, 354, 265], "home",
            bbox_history=[[294, 215, 344, 265], [304, 215, 354, 265]],
            pitch_pos=(50.0, 34.0),
        )
        away = make_track(2, [323, 215, 373, 265], "away", pitch_pos=(53.0, 34.0))
        events = PressAnalyser(homography=identity_homography).detect_press_events(
            [make_frame(0, [home, away])]
        )
        assert isinstance(events, list)
