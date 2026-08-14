"""
utils/homography.py

Camera-to-pitch homography for converting broadcast pixel coordinates
to real-world pitch metres (and back).

Usage:
    h = PitchHomography()
    h.fit(frame)                            # auto-detect from pitch lines
    pitch_pos = h.pixel_to_pitch(px)        # (x_px, y_px) → (x_m, y_m)
    pixel_pos = h.pitch_to_pixel(pt)        # (x_m, y_m) → (x_px, y_px)

    # Or supply manually annotated pitch corners (TL → TR → BR → BL)
    h.fit_from_corners(pixel_corners)

    # Or supply explicit correspondences
    h.fit_from_points(pixel_pts, pitch_pts)
"""

from __future__ import annotations

import cv2
import numpy as np
from typing import Optional
from loguru import logger

from config.settings import settings

# Pitch grass background colour (BGR).
_PITCH_GREEN_BGR: tuple[int, int, int] = (34, 139, 34)


# ---------------------------------------------------------------------------
# Synthetic pitch renderer
# ---------------------------------------------------------------------------

def draw_pitch(
    width: int = settings.frame_width,
    height: int = settings.frame_height,
    perspective: bool = False,
    line_thickness: int = 3,
) -> np.ndarray:
    """
    Render a top-down football pitch as a BGR image.

    Args:
        width, height:    output frame dimensions in pixels
        perspective:      if True, apply a mild perspective warp to simulate
                          a broadcast camera angle (useful for stress-testing)
        line_thickness:   white line width in pixels

    Returns:
        BGR numpy array of shape (height, width, 3)
    """
    frame = np.full((height, width, 3), _PITCH_GREEN_BGR, dtype=np.uint8)

    # Pitch boundary inset (5% each side so lines are inside the frame)
    mx = int(width  * 0.05)
    my = int(height * 0.05)
    frame_pw = width  - 2 * mx   # drawable pitch width in pixels
    frame_ph = height - 2 * my   # drawable pitch height in pixels
    lw = line_thickness

    cv2.rectangle(frame, (mx, my), (mx + frame_pw, my + frame_ph), (255, 255, 255), lw)
    cv2.line(frame, (mx + frame_pw // 2, my), (mx + frame_pw // 2, my + frame_ph), (255, 255, 255), lw)

    # Centre circle (radius ≈ 9.15 m → scale to pixels)
    r = int(min(frame_pw, frame_ph) * 0.085)
    cv2.circle(frame, (mx + frame_pw // 2, my + frame_ph // 2), r, (255, 255, 255), lw)
    cv2.circle(frame, (mx + frame_pw // 2, my + frame_ph // 2), max(2, lw), (255, 255, 255), -1)

    # Penalty boxes (16.5 m each side)
    pb_w = int(frame_pw * 0.157)   # 16.5 / 105
    pb_h = int(frame_ph * 0.603)   # 41 / 68
    pb_y = my + (frame_ph - pb_h) // 2
    cv2.rectangle(frame, (mx, pb_y), (mx + pb_w, pb_y + pb_h), (255, 255, 255), lw)
    cv2.rectangle(frame, (mx + frame_pw - pb_w, pb_y), (mx + frame_pw, pb_y + pb_h), (255, 255, 255), lw)

    # 6-yard boxes (5.5 m ≈ 5% of pitch length each side)
    sb_w = int(frame_pw * 0.052)
    sb_h = int(frame_ph * 0.324)   # 22 / 68
    sb_y = my + (frame_ph - sb_h) // 2
    cv2.rectangle(frame, (mx, sb_y), (mx + sb_w, sb_y + sb_h), (255, 255, 255), lw)
    cv2.rectangle(frame, (mx + frame_pw - sb_w, sb_y), (mx + frame_pw, sb_y + sb_h), (255, 255, 255), lw)

    if not perspective:
        return frame

    # Mild perspective warp to simulate a side-on broadcast angle
    src = np.float32([[0, 0], [width, 0], [width, height], [0, height]])
    shift = int(width * 0.12)
    tilt  = int(height * 0.15)
    dst = np.float32([
        [shift,           tilt],
        [width - shift,   tilt // 2],
        [width - shift // 2, height - tilt // 2],
        [shift // 2,      height - tilt],
    ])
    M = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(frame, M, (width, height), borderValue=_PITCH_GREEN_BGR)


# ---------------------------------------------------------------------------
# Homography solver
# ---------------------------------------------------------------------------

class PitchHomography:
    """
    Maps broadcast frame pixel coordinates to real-world pitch metres.

    Two fitting modes:
    - fit(frame):                   auto-detect pitch corners via line detection
    - fit_from_points(px, pt):      supply explicit pixel↔pitch correspondences

    All pitch coordinates use the FIFA standard origin: bottom-left corner,
    x = length (0–105 m), y = width (0–68 m).

    Corner ordering throughout is TL → TR → BR → BL.
    """

    def __init__(
        self,
        pitch_length: float = settings.pitch_length,
        pitch_width: float = settings.pitch_width,
    ) -> None:
        self.pitch_length = pitch_length
        self.pitch_width  = pitch_width
        self._H: Optional[np.ndarray]     = None  # pixel → pitch
        self._H_inv: Optional[np.ndarray] = None  # pitch → pixel

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def is_fitted(self) -> bool:
        return self._H is not None

    def fit(self, frame: np.ndarray) -> bool:
        """
        Auto-detect the four pitch corners from a frame and solve homography.

        Returns True on success, False if corner detection failed.
        """
        src_pts = self._detect_pitch_corners(frame)
        if src_pts is None:
            logger.warning("PitchHomography.fit: could not detect pitch corners")
            return False
        return self._solve(src_pts, self._standard_corners())

    def fit_from_corners(self, pixel_corners: np.ndarray) -> bool:
        """
        Fit from the four pitch corners in pixel space, ordered TL → TR → BR → BL.

        The manual-annotation counterpart to fit(): the caller supplies the
        corners instead of detecting them, and they map to the standard pitch
        rectangle. Returns True on success.
        """
        if len(pixel_corners) != 4:
            raise ValueError("Need exactly 4 pitch corners, ordered TL → TR → BR → BL")
        return self._solve(np.float32(pixel_corners), self._standard_corners())

    def fit_from_points(
        self,
        pixel_pts: np.ndarray,
        pitch_pts: np.ndarray,
    ) -> bool:
        """
        Fit from manually supplied pixel↔pitch correspondences.

        Args:
            pixel_pts: (N, 2) array of pixel coordinates
            pitch_pts: (N, 2) array of corresponding pitch coordinates (metres)

        Returns True on success, False if homography could not be solved.
        Raises ValueError if fewer than 4 correspondences are supplied.
        """
        if len(pixel_pts) < 4:
            raise ValueError("Need at least 4 point correspondences")
        return self._solve(np.float32(pixel_pts), np.float32(pitch_pts))

    def pixel_to_pitch(self, pixel: np.ndarray) -> np.ndarray:
        """
        Transform a single pixel (x, y) → pitch metres (x, y).

        Hot-path note: for per-frame use, call batch_pixel_to_pitch with all
        players at once rather than looping over this method.
        """
        self._check_fitted()
        return self._apply(pixel, self._H)

    def pitch_to_pixel(self, pitch: np.ndarray) -> np.ndarray:
        """Transform pitch metres (x, y) → pixel (x, y)."""
        self._check_fitted()
        return self._apply(pitch, self._H_inv)

    def batch_pixel_to_pitch(self, pixels: np.ndarray) -> np.ndarray:
        """
        Transform (N, 2) pixel array → (N, 2) pitch metres array.

        Prefer this over repeated pixel_to_pitch calls in per-frame hot loops.
        """
        self._check_fitted()
        return self._batch_apply(pixels, self._H)

    def batch_pitch_to_pixel(self, pitches: np.ndarray) -> np.ndarray:
        """Transform (N, 2) pitch metres array → (N, 2) pixel array."""
        self._check_fitted()
        return self._batch_apply(pitches, self._H_inv)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _check_fitted(self) -> None:
        if not self.is_fitted:
            raise RuntimeError(
                "PitchHomography not fitted. Call fit() or fit_from_points() first."
            )

    def _solve(self, src: np.ndarray, dst: np.ndarray) -> bool:
        """Solve homography, store matrix + precomputed inverse."""
        H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
        if H is None:
            logger.warning("cv2.findHomography returned None")
            return False
        if mask is not None and len(mask) > 4:
            inlier_ratio = float(mask.sum()) / len(mask)
            logger.debug(f"Homography RANSAC inlier ratio: {inlier_ratio:.2f}")
            if inlier_ratio < 0.5:
                logger.warning(f"Low homography inlier ratio: {inlier_ratio:.2f}")
        self._H     = H
        self._H_inv = np.linalg.inv(H)
        return True

    @staticmethod
    def _apply(pt: np.ndarray, H: np.ndarray) -> np.ndarray:
        """Apply 3×3 homography to a single 2-D point."""
        pt_h = np.empty(3, dtype=np.float64)
        pt_h[0], pt_h[1], pt_h[2] = pt[0], pt[1], 1.0
        result = H @ pt_h
        return result[:2] / result[2]

    @staticmethod
    def _batch_apply(pts: np.ndarray, H: np.ndarray) -> np.ndarray:
        """Apply 3×3 homography to an (N, 2) array."""
        # float64 matches H's dtype; avoids hidden type promotion inside cv2
        arr = np.asarray(pts, dtype=np.float64).reshape(-1, 1, 2)
        return cv2.perspectiveTransform(arr, H).reshape(-1, 2)

    def _standard_corners(self) -> np.ndarray:
        """Four pitch corners in real-world metres (TL → TR → BR → BL)."""
        L, W = self.pitch_length, self.pitch_width
        return np.float32([[0, 0], [L, 0], [L, W], [0, W]])

    @staticmethod
    def _corners_from_bbox(x1: float, y1: float, x2: float, y2: float) -> np.ndarray:
        """Build a (4, 2) float32 corner array in TL → TR → BR → BL order."""
        return np.float32([[x1, y1], [x2, y1], [x2, y2], [x1, y2]])

    # ------------------------------------------------------------------
    # Corner detection from pitch lines
    # ------------------------------------------------------------------

    def _detect_pitch_corners(
        self, frame: np.ndarray
    ) -> Optional[np.ndarray]:
        """
        Detect the four outermost pitch corners in a frame.

        Strategy:
        1. Isolate white pitch markings via HSV thresholding
        2. Find the bounding rectangle of all white pixels
        3. Return its four corners in TL → TR → BR → BL order

        Works reliably on synthetic top-down frames and clean broadcast
        footage where the full pitch boundary is visible.
        For partial-pitch views, supply correspondences via fit_from_points().
        """
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # White pixels: low saturation (S < 60), high value (V > 180)
        lower = np.array([0,   0,   180], dtype=np.uint8)
        upper = np.array([180, 60,  255], dtype=np.uint8)
        white_mask = cv2.inRange(hsv, lower, upper)

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        white_mask = cv2.morphologyEx(white_mask, cv2.MORPH_CLOSE, kernel)

        # cv2.inRange output is binary (0 or 255) — no "> 0" comparison needed
        rows, cols = np.where(white_mask)
        if rows.size < 50:
            logger.warning("Too few white pixels detected; trying Hough fallback")
            return self._detect_corners_hough(frame)

        x1, y1 = int(cols.min()), int(rows.min())
        x2, y2 = int(cols.max()), int(rows.max())
        corners = self._corners_from_bbox(x1, y1, x2, y2)
        logger.debug(f"Detected pitch corners: {corners.tolist()}")
        return corners

    def _detect_corners_hough(
        self, frame: np.ndarray
    ) -> Optional[np.ndarray]:
        """
        Fallback: detect pitch corners via Hough line intersection.
        Used when the white-pixel bounding-box method fails.
        """
        gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        lines = cv2.HoughLinesP(
            edges,
            rho=1,
            theta=np.pi / 180,
            threshold=80,
            minLineLength=50,
            maxLineGap=20,
        )
        if lines is None or len(lines) < 4:
            return None

        pts = self._find_line_intersections(lines[:, 0])
        if len(pts) < 4:
            return None

        return self._select_outer_corners(pts, frame.shape)

    @staticmethod
    def _find_line_intersections(lines: np.ndarray) -> list[np.ndarray]:
        """Return all pairwise intersections of Hough line segments."""
        intersections = []
        for i in range(len(lines)):
            for j in range(i + 1, len(lines)):
                pt = _line_intersection(lines[i], lines[j])
                if pt is not None:
                    intersections.append(pt)
        return intersections

    @staticmethod
    def _select_outer_corners(
        pts: list[np.ndarray],
        shape: tuple,
    ) -> Optional[np.ndarray]:
        """
        Pick the four pitch corners from candidate intersection points.

        For each frame corner (TL, TR, BR, BL), selects the candidate point
        nearest to it. Returns a (4, 2) array in TL → TR → BR → BL order.
        """
        if not pts:
            return None
        arr     = np.array(pts, dtype=np.float32)
        h, w    = shape[:2]
        targets = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)

        # Vectorised: compute all four nearest-corner lookups in one pass
        dists   = np.linalg.norm(arr[:, None] - targets[None], axis=2)  # (N, 4)
        indices = dists.argmin(axis=0)                                   # (4,)
        return arr[indices]


# ---------------------------------------------------------------------------
# Line intersection utility
# ---------------------------------------------------------------------------

def _line_intersection(
    seg_a: np.ndarray,
    seg_b: np.ndarray,
) -> Optional[np.ndarray]:
    """
    Find the intersection of two infinite lines defined by segments [x1,y1,x2,y2].
    Returns (x, y) or None if lines are parallel.
    """
    x1, y1, x2, y2 = seg_a.astype(float)
    x3, y3, x4, y4 = seg_b.astype(float)

    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-6:
        return None  # parallel

    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    return np.array([x1 + t * (x2 - x1), y1 + t * (y2 - y1)])
