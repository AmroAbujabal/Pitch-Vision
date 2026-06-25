"""
tests/test_metrics/test_pitch_control_homography.py

TDD tests for homography wiring in metrics/pitch_control.py.
No torch required — imports Track from tracking.types.

Run with: pytest tests/test_metrics/test_pitch_control_homography.py -v
"""

import numpy as np

from tracking.types import Track
from metrics.pitch_control import compute_pitch_control


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_track_at_pixel(track_id: int, center_px: tuple, team: str) -> Track:
    """Track with a bbox derived from a pixel centre; no pitch_pos set."""
    cx, cy = center_px
    return Track(
        track_id=track_id,
        bbox=np.array([cx - 25, cy - 50, cx + 25, cy + 50], dtype=float),
        team=team,
    )


def make_track_at_pitch(track_id: int, pitch_pos: tuple, team: str) -> Track:
    """Track with pitch_pos pre-set (bypasses any pixel conversion)."""
    t = Track(
        track_id=track_id,
        bbox=np.array([0.0, 0.0, 50.0, 100.0]),
        team=team,
    )
    t.pitch_pos = np.array(pitch_pos, dtype=float)
    return t


# ---------------------------------------------------------------------------
# compute_pitch_control accepts homography parameter
# Fixtures identity_homography / skewed_homography from conftest.py.
# ---------------------------------------------------------------------------

class TestComputePitchControlHomographyParam:

    def test_accepts_homography_keyword(self, identity_homography):
        home = [make_track_at_pitch(1, (30.0, 20.0), "home")]
        away = [make_track_at_pitch(2, (75.0, 48.0), "away")]
        result = compute_pitch_control(0, home, away, homography=identity_homography)
        assert result is not None

    def test_none_homography_equivalent_to_omitting_it(self):
        home = [make_track_at_pitch(1, (30.0, 20.0), "home")]
        away = [make_track_at_pitch(2, (75.0, 48.0), "away")]
        r1 = compute_pitch_control(0, home, away)
        r2 = compute_pitch_control(0, home, away, homography=None)
        np.testing.assert_allclose(r1.home_surface, r2.home_surface, atol=1e-9)


# ---------------------------------------------------------------------------
# Homography is used for position conversion when pitch_pos is not set
# ---------------------------------------------------------------------------

class TestPitchControlHomographyWiring:

    def test_identity_homography_matches_naive_conversion(self, identity_homography):
        """Identity homography and naive linear give the same position → same control."""
        home_h = [make_track_at_pixel(1, (960, 540), "home")]
        away_h = [make_track_at_pixel(2, (960, 540), "away")]
        home_n = [make_track_at_pixel(1, (960, 540), "home")]
        away_n = [make_track_at_pixel(2, (960, 540), "away")]

        result_h = compute_pitch_control(0, home_h, away_h, homography=identity_homography)
        result_n = compute_pitch_control(0, home_n, away_n)
        assert abs(result_h.home_control_pct - result_n.home_control_pct) < 0.05

    def test_skewed_homography_changes_result(self, skewed_homography):
        """Skewed homography warps positions → different control surface than naive."""
        home_h = [make_track_at_pixel(1, (400, 200), "home")]
        away_h = [make_track_at_pixel(2, (1500, 900), "away")]
        home_n = [make_track_at_pixel(1, (400, 200), "home")]
        away_n = [make_track_at_pixel(2, (1500, 900), "away")]

        result_h = compute_pitch_control(0, home_h, away_h, homography=skewed_homography)
        result_n = compute_pitch_control(0, home_n, away_n)
        assert not np.allclose(result_h.home_surface, result_n.home_surface, atol=0.01)

    def test_pitch_pos_takes_precedence_over_homography(self, skewed_homography):
        """Pre-set pitch_pos bypasses homography → same result with or without it."""
        home = [make_track_at_pitch(1, (30.0, 20.0), "home")]
        away = [make_track_at_pitch(2, (75.0, 48.0), "away")]

        result_h = compute_pitch_control(0, home, away, homography=skewed_homography)
        result_n = compute_pitch_control(0, home, away)
        np.testing.assert_allclose(result_h.home_surface, result_n.home_surface, atol=1e-6)
