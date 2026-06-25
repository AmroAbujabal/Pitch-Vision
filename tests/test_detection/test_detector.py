"""
tests/test_detection/test_detector.py

Unit tests for the detection pipeline.
Run with: pytest tests/test_detection/ -v
"""

import numpy as np

from detection.detector import (
    Detection,
    FrameDetections,
    TeamColorClassifier,
)
from detection.jersey_ocr import JerseyOCR


# ---------------------------------------------------------------------------
# TeamColorClassifier tests
# ---------------------------------------------------------------------------

class TestTeamColorClassifier:

    def _make_colored_crop(self, bgr: tuple, size: tuple = (128, 64)) -> np.ndarray:
        """Create a solid-color crop."""
        crop = np.zeros((size[0], size[1], 3), dtype=np.uint8)
        crop[:] = bgr
        return crop

    def test_fit_on_crops(self):
        clf = TeamColorClassifier(n_clusters=3)
        # 9 crops: 3 red, 3 blue, 3 green
        crops = (
            [self._make_colored_crop((0, 0, 200))] * 3    # red jerseys
            + [self._make_colored_crop((200, 0, 0))] * 3  # blue jerseys
            + [self._make_colored_crop((0, 200, 0))] * 3  # green jerseys
        )
        clf.fit(crops)
        assert clf.is_fitted

    def test_predict_returns_cluster(self):
        clf = TeamColorClassifier(n_clusters=2)
        crops = (
            [self._make_colored_crop((0, 0, 200))] * 5
            + [self._make_colored_crop((200, 0, 0))] * 5
        )
        clf.fit(crops)
        cluster_id, color = clf.predict(self._make_colored_crop((0, 0, 200)))
        assert cluster_id in [0, 1]
        assert len(color) == 3

    def test_assign_team_labels(self):
        clf = TeamColorClassifier()
        clf.assign_team_labels({0: "home", 1: "away", 2: "referee"})
        assert clf.cluster_labels[0] == "home"


# ---------------------------------------------------------------------------
# FrameDetections tests
# ---------------------------------------------------------------------------

class TestFrameDetections:

    def test_player_count(self):
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        fd = FrameDetections(frame_id=0, frame=frame)
        assert fd.player_count == 0

        fd.detections.append(
            Detection(frame_id=0, bbox=np.array([100, 100, 200, 400]), confidence=0.9)
        )
        assert fd.player_count == 1


# ---------------------------------------------------------------------------
# JerseyOCR tests
# ---------------------------------------------------------------------------

class TestJerseyOCR:

    def test_parse_number_valid(self):
        ocr = JerseyOCR()
        assert ocr._parse_number("10") == 10
        assert ocr._parse_number("  7  ") == 7
        assert ocr._parse_number("No. 23") == 23

    def test_parse_number_invalid(self):
        ocr = JerseyOCR()
        assert ocr._parse_number("") is None
        assert ocr._parse_number("100") is None  # out of range
        assert ocr._parse_number("abc") is None

    def test_preprocess_crop_shape(self):
        ocr = JerseyOCR()
        crop = np.zeros((200, 80, 3), dtype=np.uint8)
        processed = ocr._preprocess_crop(crop)
        assert processed.ndim == 3
        assert processed.shape[2] == 3
