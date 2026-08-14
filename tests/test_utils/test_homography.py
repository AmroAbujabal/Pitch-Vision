"""
tests/test_utils/test_homography.py

TDD tests for utils/homography.py.
All tests use synthetic frames — no real footage required.

Run with: pytest tests/test_utils/test_homography.py -v
"""

import numpy as np
import pytest

from utils.homography import PitchHomography, draw_pitch


# ---------------------------------------------------------------------------
# Shared fixture — identity-mapped homography (640×480 px → 105×68 m)
# Reused by TestFitFromPoints, TestInverseTransform, TestBatchTransforms.
# TestFitFromSyntheticFrame overrides this with its own class-level fixture.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def fitted() -> PitchHomography:
    """PitchHomography fitted to a 640×480 frame with explicit corner correspondences."""
    W, H = 640, 480
    pixel_pts = np.float32([
        [0,   0  ],
        [W,   0  ],
        [W,   H  ],
        [0,   H  ],
    ])
    pitch_pts = np.float32([
        [0,    0   ],
        [105,  0   ],
        [105,  68  ],
        [0,    68  ],
    ])
    h = PitchHomography()
    success = h.fit_from_points(pixel_pts, pitch_pts)
    assert success
    return h


# ---------------------------------------------------------------------------
# draw_pitch
# ---------------------------------------------------------------------------

class TestDrawPitch:

    def test_returns_bgr_frame_with_correct_shape(self):
        frame = draw_pitch(width=640, height=480)
        assert frame.shape == (480, 640, 3)
        assert frame.dtype == np.uint8

    def test_frame_is_predominantly_green(self):
        """Pitch grass should be the dominant colour."""
        frame = draw_pitch(width=640, height=480)
        green_channel = frame[:, :, 1]
        red_channel   = frame[:, :, 2]
        assert green_channel.mean() > red_channel.mean()

    def test_frame_contains_white_lines(self):
        """Pitch markings must be present as white pixels."""
        frame = draw_pitch(width=640, height=480)
        white_mask = np.all(frame > 200, axis=2)
        assert white_mask.sum() > 100

    def test_perspective_frame_has_correct_shape(self):
        frame = draw_pitch(width=640, height=480, perspective=True)
        assert frame.shape == (480, 640, 3)


# ---------------------------------------------------------------------------
# PitchHomography — construction and state
# ---------------------------------------------------------------------------

class TestPitchHomographyState:

    def test_not_fitted_by_default(self):
        h = PitchHomography()
        assert not h.is_fitted

    def test_fitted_after_fit(self):
        frame = draw_pitch(width=640, height=480)
        h = PitchHomography()
        h.fit(frame)
        assert h.is_fitted

    def test_pixel_to_pitch_raises_if_not_fitted(self):
        h = PitchHomography()
        with pytest.raises(RuntimeError, match="not fitted"):
            h.pixel_to_pitch(np.array([100.0, 100.0]))

    def test_pitch_to_pixel_raises_if_not_fitted(self):
        h = PitchHomography()
        with pytest.raises(RuntimeError, match="not fitted"):
            h.pitch_to_pixel(np.array([52.5, 34.0]))


# ---------------------------------------------------------------------------
# PitchHomography — fit from explicit correspondences
# ---------------------------------------------------------------------------

class TestFitFromPoints:
    """
    Tests using manually supplied pixel↔pitch correspondences.
    Isolates transform logic from line detection.
    """

    def test_top_left_pixel_maps_to_pitch_origin(self, fitted):
        result = fitted.pixel_to_pitch(np.array([0.0, 0.0]))
        np.testing.assert_allclose(result, [0.0, 0.0], atol=0.5)

    def test_top_right_pixel_maps_to_far_corner(self, fitted):
        result = fitted.pixel_to_pitch(np.array([640.0, 0.0]))
        np.testing.assert_allclose(result, [105.0, 0.0], atol=0.5)

    def test_centre_pixel_maps_to_pitch_centre(self, fitted):
        result = fitted.pixel_to_pitch(np.array([320.0, 240.0]))
        np.testing.assert_allclose(result, [52.5, 34.0], atol=0.5)

    def test_bottom_right_pixel_maps_to_far_corner(self, fitted):
        result = fitted.pixel_to_pitch(np.array([640.0, 480.0]))
        np.testing.assert_allclose(result, [105.0, 68.0], atol=0.5)


# ---------------------------------------------------------------------------
# PitchHomography — inverse transform
# ---------------------------------------------------------------------------

class TestInverseTransform:

    def test_pitch_origin_maps_to_top_left_pixel(self, fitted):
        result = fitted.pitch_to_pixel(np.array([0.0, 0.0]))
        np.testing.assert_allclose(result, [0.0, 0.0], atol=1.0)

    def test_pitch_centre_maps_to_centre_pixel(self, fitted):
        result = fitted.pitch_to_pixel(np.array([52.5, 34.0]))
        np.testing.assert_allclose(result, [320.0, 240.0], atol=1.0)

    def test_roundtrip_pixel_to_pitch_and_back(self, fitted):
        original = np.array([200.0, 150.0])
        pitch    = fitted.pixel_to_pitch(original)
        recovered = fitted.pitch_to_pixel(pitch)
        np.testing.assert_allclose(recovered, original, atol=1.0)

    def test_roundtrip_pitch_to_pixel_and_back(self, fitted):
        original  = np.array([30.0, 20.0])
        pixel     = fitted.pitch_to_pixel(original)
        recovered = fitted.pixel_to_pitch(pixel)
        np.testing.assert_allclose(recovered, original, atol=0.5)


# ---------------------------------------------------------------------------
# PitchHomography — batch transforms
# ---------------------------------------------------------------------------

class TestBatchTransforms:

    def test_batch_pixel_to_pitch_shape(self, fitted):
        pixels = np.array([[0., 0.], [320., 240.], [640., 480.]])
        result = fitted.batch_pixel_to_pitch(pixels)
        assert result.shape == (3, 2)

    def test_batch_pixel_to_pitch_values(self, fitted):
        pixels = np.array([[0., 0.], [320., 240.], [640., 480.]])
        result = fitted.batch_pixel_to_pitch(pixels)
        np.testing.assert_allclose(result[0], [0.,    0.  ], atol=0.5)
        np.testing.assert_allclose(result[1], [52.5,  34. ], atol=0.5)
        np.testing.assert_allclose(result[2], [105.,  68. ], atol=0.5)

    def test_batch_pitch_to_pixel_shape(self, fitted):
        pitches = np.array([[0., 0.], [52.5, 34.], [105., 68.]])
        result  = fitted.batch_pitch_to_pixel(pitches)
        assert result.shape == (3, 2)

    def test_batch_raises_if_not_fitted(self):
        h = PitchHomography()
        with pytest.raises(RuntimeError, match="not fitted"):
            h.batch_pixel_to_pitch(np.array([[0., 0.]]))


# ---------------------------------------------------------------------------
# PitchHomography — fit from synthetic frame
# ---------------------------------------------------------------------------

class TestFitFromSyntheticFrame:
    """
    End-to-end: fit() detects corners from a drawn pitch and solves homography.
    Tolerances are looser here since line detection introduces noise.
    """

    @pytest.fixture
    def fitted(self) -> PitchHomography:
        frame = draw_pitch(width=640, height=480)
        h = PitchHomography()
        success = h.fit(frame)
        assert success, "fit() failed to detect pitch corners"
        return h

    def test_centre_pixel_near_pitch_centre(self, fitted):
        result = fitted.pixel_to_pitch(np.array([320.0, 240.0]))
        assert abs(result[0] - 52.5) < 8.0
        assert abs(result[1] - 34.0) < 8.0

    def test_top_left_near_pitch_origin(self, fitted):
        # Small inset to avoid the exact-edge white line
        result = fitted.pixel_to_pitch(np.array([10.0, 10.0]))
        assert result[0] < 15.0
        assert result[1] < 15.0

    def test_roundtrip_survives_line_detection(self, fitted):
        pixel = np.array([200.0, 150.0])
        pitch = fitted.pixel_to_pitch(pixel)
        back  = fitted.pitch_to_pixel(pitch)
        np.testing.assert_allclose(back, pixel, atol=3.0)


# ---------------------------------------------------------------------------
# fit_from_corners — manual pitch corner annotations
# ---------------------------------------------------------------------------

# A tilted touchline view: the far touchline is shorter than the near one.
TOUCHLINE_CORNERS = np.float32([
    [200.0,  300.0],   # TL
    [1720.0, 300.0],   # TR
    [1900.0, 950.0],   # BR
    [20.0,   950.0],   # BL
])


class TestFitFromCorners:

    @pytest.fixture(scope="class")
    def fitted_corners(self) -> PitchHomography:
        h = PitchHomography()
        assert h.fit_from_corners(TOUCHLINE_CORNERS)
        return h

    def test_corners_map_to_the_standard_pitch_rectangle(self, fitted_corners):
        mapped = fitted_corners.batch_pixel_to_pitch(TOUCHLINE_CORNERS)
        np.testing.assert_allclose(
            mapped,
            np.array([[0, 0], [105, 0], [105, 68], [0, 68]], dtype=float),
            atol=1e-3,
        )

    def test_x_is_the_length_axis(self, fitted_corners):
        """Convention check: x spans 0-105 (goal to goal), y spans 0-68."""
        mapped = fitted_corners.batch_pixel_to_pitch(TOUCHLINE_CORNERS)
        assert mapped[:, 0].max() > mapped[:, 1].max()

    def test_wrong_corner_count_raises(self):
        with pytest.raises(ValueError):
            PitchHomography().fit_from_corners(TOUCHLINE_CORNERS[:3])


# ---------------------------------------------------------------------------
# Cross-module contract: homography output feeds formation detection
# ---------------------------------------------------------------------------

class TestCornersToFormation:
    """
    The pipeline projects tracked players through fit_from_corners() and hands
    the result to detect_formation(). Both modules must agree that depth is the
    x axis — if either flips, the shape collapses into a single line. This test
    is the guard on that shared convention.
    """

    # 4-3-3 defending the low-x end: GK, back four, midfield three, front three.
    LAYOUT_433 = np.array([
        [5.0, 34.0],
        [22.0, 10.0], [22.0, 26.0], [22.0, 42.0], [22.0, 58.0],
        [52.0, 20.0], [52.0, 34.0], [52.0, 48.0],
        [80.0, 14.0], [80.0, 34.0], [80.0, 54.0],
    ])

    def test_shape_survives_a_projection_round_trip(self):
        from tracking.types import Track, TrackedFrame
        from metrics.formation import detect_formation

        h = PitchHomography()
        assert h.fit_from_corners(TOUCHLINE_CORNERS)

        # Pitch metres -> camera pixels (what a detector would see) -> back.
        pixels = h.batch_pitch_to_pixel(self.LAYOUT_433)
        recovered = h.batch_pixel_to_pitch(pixels)

        tracks = []
        for i, pos in enumerate(recovered):
            t = Track(track_id=i, bbox=np.zeros(4, dtype=float), team="home")
            t.is_confirmed = True
            t.pitch_history = [pos]
            tracks.append(t)

        frames = [TrackedFrame(frame_id=f, tracks=tracks) for f in range(3)]
        assert detect_formation(
            frames, team="home", own_goal_end="low"
        ) == "4-3-3"
