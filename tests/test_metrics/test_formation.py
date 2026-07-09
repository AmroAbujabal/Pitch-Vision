"""
tests/test_metrics/test_formation.py

TDD tests for metrics/formation.py.
No torch/cv2 required — imports Track/TrackedFrame from tracking.types.

Run with: pytest tests/test_metrics/test_formation.py -v
"""

import numpy as np
import pytest

from tracking.types import Track, TrackedFrame
from metrics.formation import detect_formation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_track(track_id: int, team: str, pitch_pos: tuple) -> Track:
    t = Track(track_id=track_id, bbox=np.zeros(4, dtype=float), team=team)
    t.is_confirmed = True
    t.pitch_pos = np.array(pitch_pos, dtype=float)
    return t


def make_team(team: str, positions: list, start_id: int = 0) -> list:
    """One confirmed track per (x, y) position tuple."""
    return [make_track(start_id + i, team, pos) for i, pos in enumerate(positions)]


def frames_from(tracks: list, n_frames: int = 3) -> list:
    """Repeat the same static tracks across n_frames (mean position == pitch_pos)."""
    return [TrackedFrame(frame_id=f, tracks=tracks) for f in range(n_frames)]


# Canonical layouts. Pitch is 105 (x, width) × 68 (y, length used as depth).
# GK sits nearest own goal (low y); lines advance up-pitch. own_goal_end="low".
def layout_442() -> list:
    return make_team("home", [
        (52, 4),                                   # GK
        (15, 20), (38, 20), (67, 20), (90, 20),    # 4 defenders
        (15, 45), (38, 45), (67, 45), (90, 45),    # 4 midfielders
        (38, 66), (67, 66),                        # 2 forwards
    ])


def layout_433() -> list:
    return make_team("home", [
        (52, 4),                                   # GK
        (15, 20), (38, 20), (67, 20), (90, 20),    # 4 defenders
        (30, 45), (52, 45), (75, 45),              # 3 midfielders
        (20, 66), (52, 66), (85, 66),              # 3 forwards
    ])


# ---------------------------------------------------------------------------
# Direction is required — no guessing when it is unknown
# ---------------------------------------------------------------------------

class TestDirectionRequired:

    def test_unknown_direction_returns_unknown(self):
        # A perfectly clean 4-4-2 still yields "unknown" without a direction.
        assert detect_formation(frames_from(layout_442()), team="home") == "unknown"

    def test_invalid_direction_returns_unknown(self):
        assert detect_formation(
            frames_from(layout_442()), team="home", own_goal_end="sideways"
        ) == "unknown"


# ---------------------------------------------------------------------------
# Core detection (direction supplied)
# ---------------------------------------------------------------------------

class TestFormationDetection:

    def test_detects_4_4_2(self):
        assert detect_formation(
            frames_from(layout_442()), team="home", own_goal_end="low"
        ) == "4-4-2"

    def test_detects_4_3_3(self):
        assert detect_formation(
            frames_from(layout_433()), team="home", own_goal_end="low"
        ) == "4-3-3"

    def test_detects_when_team_defends_high_y_end(self):
        """Away team attacks the opposite direction (own goal at high y).
        Formation string is still reported defence -> attack."""
        positions = [(x, 68 - y) for (x, y) in [
            (52, 4),
            (15, 20), (38, 20), (67, 20), (90, 20),
            (15, 45), (38, 45), (67, 45), (90, 45),
            (38, 66), (67, 66),
        ]]
        away = make_team("away", positions)
        assert detect_formation(
            frames_from(away), team="away", own_goal_end="high"
        ) == "4-4-2"

    def test_lone_striker_shape_resolved_by_direction(self):
        """Regression: a 4-5-1 with an isolated striker used to be reversed to
        '5-4-1' by gap-based orientation. With direction known it is correct."""
        team = make_team("home", [
            (52, 4),                                       # GK
            (15, 20), (38, 20), (67, 20), (90, 20),        # 4 defenders
            (10, 45), (32, 45), (52, 45), (72, 45), (94, 45),  # 5 midfielders
            (52, 66),                                      # lone striker
        ])
        assert detect_formation(
            frames_from(team), team="home", own_goal_end="low"
        ) == "4-5-1"

    def test_ignores_other_team_tracks(self):
        home = layout_442()
        away = make_team("away", [(10, 10), (50, 50), (90, 30)], start_id=100)
        frames = frames_from(home + away)
        assert detect_formation(frames, team="home", own_goal_end="low") == "4-4-2"

    def test_ignores_unconfirmed_tracks(self):
        home = layout_442()
        ghost = make_track(200, "home", (52, 34))
        ghost.is_confirmed = False
        frames = frames_from(home + [ghost])
        assert detect_formation(frames, team="home", own_goal_end="low") == "4-4-2"


# ---------------------------------------------------------------------------
# Goalkeeper handling
# ---------------------------------------------------------------------------

class TestGoalkeeper:

    def test_keeper_off_camera_keeps_all_outfielders(self):
        """No isolated keeper present -> do NOT drop a real defender as GK."""
        outfield_only = make_team("home", [
            (15, 20), (38, 20), (67, 20), (90, 20),    # 4 defenders (deepest)
            (30, 45), (52, 45), (75, 45),              # 3 midfielders
            (20, 66), (52, 66), (85, 66),              # 3 forwards
        ])
        # 10 outfielders, no keeper -> "4-3-3", not "3-3-3" with a dropped back.
        assert detect_formation(
            frames_from(outfield_only), team="home", own_goal_end="low"
        ) == "4-3-3"

    def test_isolated_keeper_is_dropped(self):
        assert detect_formation(
            frames_from(layout_442()), team="home", own_goal_end="low"
        ) == "4-4-2"  # 11 tracks -> 10 outfield after GK removed


# ---------------------------------------------------------------------------
# Line clustering tolerance
# ---------------------------------------------------------------------------

class TestLineTolerance:

    def test_intra_line_stagger_not_oversplit(self):
        """Regression: wingers at 62 and a striker at 66 (a normal stagger)
        must stay one line, not split into '4-3-2-1'."""
        team = make_team("home", [
            (52, 4),                                   # GK
            (15, 20), (38, 20), (67, 20), (90, 20),    # 4 defenders
            (30, 42), (52, 42), (75, 42),              # 3 midfielders
            (18, 62), (86, 62), (52, 66),              # wingers + advanced striker
        ])
        assert detect_formation(
            frames_from(team), team="home", own_goal_end="low"
        ) == "4-3-3"


# ---------------------------------------------------------------------------
# Unknown / degenerate cases
# ---------------------------------------------------------------------------

class TestUnknownCases:

    def test_empty_frames_returns_unknown(self):
        assert detect_formation([], team="home", own_goal_end="low") == "unknown"

    def test_too_few_players_returns_unknown(self):
        few = make_team("home", [(52, 4), (20, 20), (60, 20)])  # 3 < min_players
        assert detect_formation(
            frames_from(few), team="home", own_goal_end="low"
        ) == "unknown"

    def test_team_with_no_positions_returns_unknown(self):
        tracks = []
        for i in range(6):
            t = Track(track_id=i, bbox=np.zeros(4), team="home")
            t.is_confirmed = True
            tracks.append(t)
        assert detect_formation(
            frames_from(tracks), team="home", own_goal_end="low"
        ) == "unknown"

    def test_single_player_low_min_players_does_not_crash(self):
        """Regression: min_players=1 + a single track used to IndexError in
        orientation. It must return 'unknown' instead."""
        one = make_team("home", [(52, 4)])
        assert detect_formation(
            frames_from(one), team="home", own_goal_end="low", min_players=1
        ) == "unknown"


# ---------------------------------------------------------------------------
# Aggregation across frames
# ---------------------------------------------------------------------------

class TestAggregation:

    def test_averages_positions_across_frames(self):
        base = layout_442()
        frames = []
        for f, dy in enumerate([-2.0, 0.0, 2.0]):  # symmetric jitter -> mean unchanged
            jittered = [
                make_track(t.track_id, "home", (t.pitch_pos[0], t.pitch_pos[1] + dy))
                for t in base
            ]
            frames.append(TrackedFrame(frame_id=f, tracks=jittered))
        assert detect_formation(frames, team="home", own_goal_end="low") == "4-4-2"


# ---------------------------------------------------------------------------
# Output contract
# ---------------------------------------------------------------------------

class TestOutputContract:

    def test_returns_str(self):
        result = detect_formation(
            frames_from(layout_442()), team="home", own_goal_end="low"
        )
        assert isinstance(result, str)

    def test_line_counts_sum_to_outfield_players(self):
        result = detect_formation(
            frames_from(layout_433()), team="home", own_goal_end="low"
        )
        total = sum(int(n) for n in result.split("-"))
        assert total == 10  # 11 players minus the goalkeeper
