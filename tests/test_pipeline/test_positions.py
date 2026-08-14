"""
tests/test_pipeline/test_positions.py

Tests for the pure helpers in scripts/run_pipeline.py — the pixel→pitch inputs
and the defended-end mapping. The pipeline's heavy stages need torch; these
helpers deliberately do not, so they are covered here.

Run with: pytest tests/test_pipeline/test_positions.py -v
"""

import numpy as np

from scripts.run_pipeline import (
    _OPPOSITE_END,
    PITCH_MARGIN_M,
    clamp_to_pitch,
    feet_pixels,
)


class TestFeetPixels:

    def test_uses_bottom_edge_at_mid_width(self):
        # [x1, y1, x2, y2] — feet are (mid-x, y2), not the box centre.
        result = feet_pixels([np.array([10.0, 20.0, 30.0, 80.0])])
        np.testing.assert_allclose(result, [[20.0, 80.0]])

    def test_is_not_the_box_centre(self):
        """Regression guard: the centre would put the player at y=50 here."""
        result = feet_pixels([np.array([10.0, 20.0, 30.0, 80.0])])
        assert result[0][1] == 80.0

    def test_preserves_one_row_per_frame(self):
        history = [
            np.array([0.0, 0.0, 10.0, 10.0]),
            np.array([10.0, 10.0, 20.0, 30.0]),
            np.array([20.0, 20.0, 40.0, 60.0]),
        ]
        result = feet_pixels(history)
        assert result.shape == (3, 2)
        np.testing.assert_allclose(result, [[5.0, 10.0], [15.0, 30.0], [30.0, 60.0]])


class TestOppositeEnd:

    def test_teams_defend_opposite_ends(self):
        assert _OPPOSITE_END["low"] == "high"
        assert _OPPOSITE_END["high"] == "low"

    def test_unknown_end_has_no_opposite(self):
        """No direction for home means none for away either — both formations
        then come back "unknown" rather than guessed."""
        assert _OPPOSITE_END.get("") is None


class TestClampToPitch:

    def test_leaves_on_pitch_positions_untouched(self):
        pos = np.array([[0.0, 0.0], [52.5, 34.0], [105.0, 68.0]])
        np.testing.assert_allclose(clamp_to_pitch(pos, 105.0, 68.0), pos)

    def test_allows_play_just_off_the_pitch(self):
        """Throw-ins, keepers behind their line and corner takers are all
        legitimately outside the painted rectangle."""
        pos = np.array([[-2.0, -2.0], [107.0, 70.0]])
        np.testing.assert_allclose(clamp_to_pitch(pos, 105.0, 68.0), pos)

    def test_clamps_far_off_pitch_projections(self):
        """A point past the horizon projected to -28 m must not become metres of
        travel in the physical metrics."""
        result = clamp_to_pitch(np.array([[52.5, -27.9]]), 105.0, 68.0)
        assert result[0][1] == -PITCH_MARGIN_M

    def test_non_finite_holds_the_previous_position(self):
        pos = np.array([[10.0, 20.0], [np.inf, np.nan], [12.0, 22.0]])
        result = clamp_to_pitch(pos, 105.0, 68.0)
        np.testing.assert_allclose(result[1], [10.0, 20.0])
        assert np.isfinite(result).all()

    def test_leading_non_finite_falls_back_to_origin(self):
        """No previous position to hold, so it must still come back finite."""
        result = clamp_to_pitch(np.array([[np.inf, np.inf], [5.0, 5.0]]), 105.0, 68.0)
        np.testing.assert_allclose(result[0], [0.0, 0.0])

    def test_does_not_mutate_its_input(self):
        pos = np.array([[999.0, 999.0]])
        clamp_to_pitch(pos, 105.0, 68.0)
        np.testing.assert_allclose(pos, [[999.0, 999.0]])
