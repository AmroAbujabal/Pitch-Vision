"""
tests/test_metrics/test_formation.py

TDD tests for metrics/formation.py.
No torch/cv2 required — imports Track/TrackedFrame from tracking.types.

Run with: pytest tests/test_metrics/test_formation.py -v
"""

import numpy as np

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
    """Repeat the same static tracks across n_frames.

    Mirrors production: the tracker puts the *same* Track objects in every
    TrackedFrame, so a track's position is read once, not once per frame.
    """
    return [TrackedFrame(frame_id=f, tracks=tracks) for f in range(n_frames)]


# Canonical layouts in project pitch coordinates: x = length (goal-to-goal,
# 0-105 m) is the depth axis, y = width (0-68 m) is lateral. GK sits nearest the
# own goal (low x); lines advance up-pitch. own_goal_end="low".
def layout_442() -> list:
    return make_team("home", [
        (5, 34),                                   # GK
        (22, 10), (22, 26), (22, 42), (22, 58),    # 4 defenders
        (52, 10), (52, 26), (52, 42), (52, 58),    # 4 midfielders
        (80, 26), (80, 42),                        # 2 forwards
    ])


def layout_433() -> list:
    return make_team("home", [
        (5, 34),                                   # GK
        (22, 10), (22, 26), (22, 42), (22, 58),    # 4 defenders
        (52, 20), (52, 34), (52, 48),              # 3 midfielders
        (80, 14), (80, 34), (80, 54),              # 3 forwards
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

    def test_detects_when_team_defends_high_x_end(self):
        """Away team attacks the opposite direction (own goal at high x).
        Formation string is still reported defence -> attack."""
        positions = [(105 - x, y) for (x, y) in [
            (5, 34),
            (22, 10), (22, 26), (22, 42), (22, 58),
            (52, 10), (52, 26), (52, 42), (52, 58),
            (80, 26), (80, 42),
        ]]
        away = make_team("away", positions)
        assert detect_formation(
            frames_from(away), team="away", own_goal_end="high"
        ) == "4-4-2"

    def test_lone_striker_shape_resolved_by_direction(self):
        """Regression: a 4-5-1 with an isolated striker used to be reversed to
        '5-4-1' by gap-based orientation. With direction known it is correct."""
        team = make_team("home", [
            (5, 34),                                           # GK
            (22, 10), (22, 26), (22, 42), (22, 58),            # 4 defenders
            (52, 6), (52, 20), (52, 34), (52, 48), (52, 62),   # 5 midfielders
            (80, 34),                                          # lone striker
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
        ghost = make_track(200, "home", (34, 52))
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
            (22, 10), (22, 26), (22, 42), (22, 58),    # 4 defenders (deepest)
            (52, 20), (52, 34), (52, 48),              # 3 midfielders
            (80, 14), (80, 34), (80, 54),              # 3 forwards
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
        """Regression: wingers at 72 and a striker at 80 (a normal stagger)
        must stay one line, not split into '4-3-2-1'."""
        team = make_team("home", [
            (5, 34),                                   # GK
            (22, 10), (22, 26), (22, 42), (22, 58),    # 4 defenders
            (48, 20), (48, 34), (48, 48),              # 3 midfielders
            (72, 14), (72, 54), (80, 34),              # wingers + advanced striker
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
        few = make_team("home", [(5, 34), (22, 20), (22, 48)])  # 3 < min_players
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
        one = make_team("home", [(5, 34)])
        assert detect_formation(
            frames_from(one), team="home", own_goal_end="low", min_players=1
        ) == "unknown"


# ---------------------------------------------------------------------------
# Aggregation across frames
# ---------------------------------------------------------------------------

class TestAggregation:

    def test_uses_mean_of_pitch_history(self):
        """Depth is the mean over a track's pitch_history, not its latest
        position. pitch_pos here is a misleading final-frame snapshot with the
        whole team bunched on halfway — using it would collapse the shape."""
        tracks = []
        for t in layout_442():
            depth, lateral = t.pitch_pos
            # Symmetric jitter around the true depth -> mean is unchanged.
            t.pitch_history = [
                np.array([depth + d, lateral], dtype=float) for d in (-2.0, 0.0, 2.0)
            ]
            t.pitch_pos = np.array([52.0, lateral], dtype=float)
            tracks.append(t)
        assert detect_formation(
            frames_from(tracks), team="home", own_goal_end="low"
        ) == "4-4-2"

    def test_falls_back_to_pitch_pos_without_history(self):
        assert detect_formation(
            frames_from(layout_442()), team="home", own_goal_end="low"
        ) == "4-4-2"


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


# ---------------------------------------------------------------------------
# Half-time end swap
# ---------------------------------------------------------------------------

def with_history(tracks: list, frames: list, mirror_from: int | None = None) -> list:
    """Give every track a pitch_history observed at *frames*.

    Positions come from each track's pitch_pos. When *mirror_from* is given,
    observations at or after that frame are mirrored along the length axis —
    which is exactly what a real second half looks like once the teams change
    ends, since the camera does not move.
    """
    for t in tracks:
        depth, lateral = t.pitch_pos
        history = []
        for f in frames:
            x = 105.0 - depth if mirror_from is not None and f >= mirror_from else depth
            history.append(np.array([x, lateral], dtype=float))
        t.pitch_history = history
        t.frame_history = list(frames)
    return tracks


class TestHalfTimeEndSwap:

    def test_swapped_second_half_is_corrected(self):
        """The teams change ends at frame 100. With the split declared, the
        4-4-2 is still a 4-4-2."""
        tracks = with_history(layout_442(), frames=[0, 50, 150, 199], mirror_from=100)
        assert detect_formation(
            frames_from(tracks), team="home",
            own_goal_end="low", half_time_frame=100,
        ) == "4-4-2"

    def test_without_the_split_the_same_match_is_wrong(self):
        """States the bug: the identical data, with no half-time mark, averages
        each player's two ends together and collapses the shape."""
        tracks = with_history(layout_442(), frames=[0, 50, 150, 199], mirror_from=100)
        assert detect_formation(
            frames_from(tracks), team="home", own_goal_end="low",
        ) != "4-4-2"

    def test_a_wrong_split_gives_a_wrong_answer(self):
        """The risk this feature takes on, stated as a test.

        A declared split is trusted. Positions that did not actually swap get
        their second half mirrored, which averages every player with their own
        mirror and collapses the shape. Nothing server-side can detect this —
        the only mitigation is that the coach types the mark while watching the
        video. Pinned so that a future "helpful" attempt to infer or correct
        the split has to argue with this test rather than pass silently.
        """
        tracks = with_history(layout_442(), frames=[0, 50, 150, 199])
        assert detect_formation(
            frames_from(tracks), team="home",
            own_goal_end="low", half_time_frame=100,
        ) != "4-4-2"

    def test_observation_on_the_boundary_is_second_half(self):
        """Off-by-one here is a silent half-swap, so the boundary is pinned.

        Every observation sits exactly on the split and is mirrored. Reading
        the boundary as second-half orients all of them correctly; reading it
        as first-half mirrors the whole match into 2-4-4.
        """
        tracks = with_history(layout_442(), frames=[100, 100, 100], mirror_from=100)
        assert detect_formation(
            frames_from(tracks), team="home",
            own_goal_end="low", half_time_frame=100,
        ) == "4-4-2"

    def test_away_team_swaps_the_other_way(self):
        """The away team starts at the high end and ends at the low one."""
        positions = [(105 - x, y) for (x, y) in [
            (5, 34),
            (22, 10), (22, 26), (22, 42), (22, 58),
            (52, 10), (52, 26), (52, 42), (52, 58),
            (80, 26), (80, 42),
        ]]
        tracks = with_history(
            make_team("away", positions), frames=[0, 150], mirror_from=100
        )
        assert detect_formation(
            frames_from(tracks), team="away",
            own_goal_end="high", half_time_frame=100,
        ) == "4-4-2"

    def test_observations_without_a_frame_are_first_half(self):
        """pitch_history with no frame_history cannot be attributed, so it
        takes the first half's direction — today's behaviour."""
        tracks = layout_442()
        for t in tracks:
            t.pitch_history = [np.asarray(t.pitch_pos, dtype=float)]
            t.frame_history = []
        assert detect_formation(
            frames_from(tracks), team="home",
            own_goal_end="low", half_time_frame=100,
        ) == "4-4-2"
