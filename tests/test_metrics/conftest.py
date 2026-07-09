"""
tests/test_metrics/conftest.py

Shared fixtures for metrics test modules.
"""

import numpy as np
import pytest

# NOTE: PitchHomography is imported lazily inside each fixture because
# utils.homography pulls in cv2. Importing it at module scope would fail
# collection of the whole test_metrics/ directory (breaking cv2-free tests
# like test_formation.py) in environments without opencv installed.


@pytest.fixture(scope="module")
def identity_homography():
    """1920×1080 pixel frame mapped linearly to 105×68 m pitch."""
    from utils.homography import PitchHomography

    h = PitchHomography()
    pixel_pts = np.float32([[0, 0], [1920, 0], [1920, 1080], [0, 1080]])
    pitch_pts  = np.float32([[0, 0], [105,  0], [105,  68],  [0,  68]])
    h.fit_from_points(pixel_pts, pitch_pts)
    return h


@pytest.fixture(scope="module")
def skewed_homography():
    """Non-identity homography — skewed quad → pitch, so results differ from naive linear."""
    from utils.homography import PitchHomography

    h = PitchHomography()
    pixel_pts = np.float32([[100, 50], [1820, 80], [1850, 1000], [80, 1020]])
    pitch_pts  = np.float32([[0, 0],   [105, 0],   [105, 68],    [0, 68]])
    h.fit_from_points(pixel_pts, pitch_pts)
    return h
