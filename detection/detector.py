"""
detection/detector.py

Stage 1: Detect all players on a pitch frame using YOLOv10,
then segment each player mask using SAM 2.

Output per frame:
    List[Detection] — bounding boxes, masks, team color, confidence
"""

from __future__ import annotations

import cv2
import numpy as np
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from loguru import logger
from ultralytics import YOLO

from config.settings import settings


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Detection:
    """Single player detection in one frame."""
    frame_id: int
    bbox: np.ndarray          # [x1, y1, x2, y2] in pixels
    mask: Optional[np.ndarray] = None   # H x W binary mask from SAM 2
    confidence: float = 0.0
    class_id: int = 0         # 0 = person
    team: Optional[str] = None          # "home" | "away" | "referee" | None
    team_color: Optional[tuple] = None  # dominant BGR color of jersey
    crop: Optional[np.ndarray] = None   # cropped player image for Re-ID


@dataclass
class FrameDetections:
    """All detections for a single frame."""
    frame_id: int
    frame: np.ndarray
    detections: list[Detection] = field(default_factory=list)

    @property
    def player_count(self) -> int:
        return len(self.detections)


# ---------------------------------------------------------------------------
# Team color classifier
# ---------------------------------------------------------------------------

class TeamColorClassifier:
    """
    Classifies players into home/away/referee using dominant jersey color.
    Uses KMeans on the upper-body crop HSV histogram.
    Fitted lazily on the first N frames of a match.
    """

    def __init__(self, n_clusters: int = 3):
        from sklearn.cluster import KMeans
        self.n_clusters = n_clusters          # home, away, referee
        self.kmeans: Optional[KMeans] = None
        self.cluster_labels: dict[int, str] = {}
        self.is_fitted = False

    def extract_dominant_color(self, crop: np.ndarray) -> np.ndarray:
        """Return dominant HSV color of the upper 60% of a player crop."""
        h = crop.shape[0]
        upper = crop[: int(h * 0.6), :]       # jersey, not shorts
        hsv = cv2.cvtColor(upper, cv2.COLOR_BGR2HSV)

        # Flatten and sample pixels (skip near-white/black — likely background)
        pixels = hsv.reshape(-1, 3).astype(np.float32)
        mask = (pixels[:, 1] > 30) & (pixels[:, 2] > 50)  # S > 30, V > 50
        pixels = pixels[mask]

        if len(pixels) < 10:
            return np.array([0.0, 0.0, 128.0])  # grey fallback

        # Return mean hue/sat/val of remaining pixels
        return pixels.mean(axis=0)

    def fit(self, crops: list[np.ndarray]) -> None:
        from sklearn.cluster import KMeans
        colors = np.array([self.extract_dominant_color(c) for c in crops])
        self.kmeans = KMeans(n_clusters=self.n_clusters, n_init=10, random_state=42)
        self.kmeans.fit(colors)
        self.is_fitted = True
        logger.info(f"TeamColorClassifier fitted on {len(crops)} crops")

    def predict(self, crop: np.ndarray) -> tuple[int, np.ndarray]:
        """Returns (cluster_id, dominant_color)."""
        color = self.extract_dominant_color(crop)
        if not self.is_fitted or self.kmeans is None:
            return 0, color
        cluster = int(self.kmeans.predict(color.reshape(1, -1))[0])
        return cluster, color

    def assign_team_labels(self, label_map: dict[int, str]) -> None:
        """
        Manually map cluster IDs to team labels after fitting.
        Example: {0: "home", 1: "away", 2: "referee"}
        """
        self.cluster_labels = label_map


# ---------------------------------------------------------------------------
# Main detector
# ---------------------------------------------------------------------------

class PlayerDetector:
    """
    Detects players in a video frame using YOLOv10.
    Optionally segments each detection with SAM 2.
    """

    PERSON_CLASS_ID = 0  # COCO class index for 'person'

    def __init__(
        self,
        use_sam: bool = True,
        team_classifier: Optional[TeamColorClassifier] = None,
    ):
        self.device = settings.device
        self.use_sam = use_sam
        self.team_classifier = team_classifier or TeamColorClassifier()

        logger.info("Loading YOLO model...")
        self.yolo = YOLO(settings.yolo_model)
        self.yolo.to(self.device)

        self.sam_predictor = None
        if use_sam:
            self._load_sam2()

    def _load_sam2(self) -> None:
        """Load SAM 2 predictor. Requires sam2 package installed."""
        try:
            from sam2.build_sam import build_sam2
            from sam2.sam2_image_predictor import SAM2ImagePredictor

            weights_path = settings.weights_dir / settings.sam2_model
            config_path = settings.sam2_config

            sam2_model = build_sam2(config_path, str(weights_path), device=self.device)
            self.sam_predictor = SAM2ImagePredictor(sam2_model)
            logger.info("SAM 2 loaded successfully")

        except ImportError:
            logger.warning("SAM 2 not installed — running without segmentation masks")
            self.use_sam = False
        except FileNotFoundError as e:
            logger.warning(f"SAM 2 weights not found: {e} — running without masks")
            self.use_sam = False

    def _get_player_crop(self, frame: np.ndarray, bbox: np.ndarray) -> np.ndarray:
        """Crop a player from a frame given bbox [x1, y1, x2, y2]."""
        x1, y1, x2, y2 = bbox.astype(int)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(frame.shape[1], x2), min(frame.shape[0], y2)
        return frame[y1:y2, x1:x2].copy()

    def _segment_with_sam(
        self, frame: np.ndarray, bboxes: np.ndarray
    ) -> list[Optional[np.ndarray]]:
        """
        Run SAM 2 on the frame with bounding box prompts.
        Returns one binary mask per bbox, or None on failure.
        """
        if self.sam_predictor is None or len(bboxes) == 0:
            return [None] * len(bboxes)

        masks = []
        self.sam_predictor.set_image(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

        for bbox in bboxes:
            try:
                # SAM 2 takes box prompt as [x1, y1, x2, y2]
                mask_out, _, _ = self.sam_predictor.predict(
                    box=bbox[None],        # add batch dim
                    multimask_output=False,
                )
                masks.append(mask_out[0].astype(np.uint8))  # H x W
            except Exception as e:
                logger.debug(f"SAM 2 mask failed for bbox {bbox}: {e}")
                masks.append(None)

        return masks

    def detect_frame(self, frame: np.ndarray, frame_id: int) -> FrameDetections:
        """
        Run full detection pipeline on a single frame.

        Args:
            frame:    BGR numpy array (H, W, 3)
            frame_id: frame index in the video

        Returns:
            FrameDetections with all detected players
        """
        result = FrameDetections(frame_id=frame_id, frame=frame)

        # --- YOLO inference ---
        yolo_results = self.yolo(
            frame,
            conf=settings.yolo_conf_threshold,
            iou=settings.yolo_iou_threshold,
            classes=[self.PERSON_CLASS_ID],
            verbose=False,
        )

        if not yolo_results or yolo_results[0].boxes is None:
            return result

        boxes_data = yolo_results[0].boxes
        bboxes = boxes_data.xyxy.cpu().numpy()   # (N, 4)
        confs = boxes_data.conf.cpu().numpy()    # (N,)

        if len(bboxes) == 0:
            return result

        # --- SAM 2 segmentation ---
        masks = self._segment_with_sam(frame, bboxes)

        # --- Build Detection objects ---
        for i, (bbox, conf) in enumerate(zip(bboxes, confs)):
            crop = self._get_player_crop(frame, bbox)

            if crop.size == 0:
                continue

            team_id, team_color = self.team_classifier.predict(crop)
            team_label = self.team_classifier.cluster_labels.get(team_id)

            detection = Detection(
                frame_id=frame_id,
                bbox=bbox,
                mask=masks[i],
                confidence=float(conf),
                class_id=self.PERSON_CLASS_ID,
                team=team_label,
                team_color=tuple(team_color.tolist()),
                crop=crop,
            )
            result.detections.append(detection)

        return result

    def process_video(
        self,
        video_path: Path,
        output_callback=None,
        max_frames: Optional[int] = None,
    ) -> list[FrameDetections]:
        """
        Process an entire video file frame by frame.

        Args:
            video_path:       path to video file
            output_callback:  optional fn(FrameDetections) called per frame
            max_frames:       stop after N frames (useful for testing)

        Returns:
            list of FrameDetections, one per frame
        """
        cap = cv2.VideoCapture(str(video_path))

        if not cap.isOpened():
            raise FileNotFoundError(f"Cannot open video: {video_path}")

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        logger.info(f"Processing {video_path.name} — {total_frames} frames @ {fps}fps")

        all_detections: list[FrameDetections] = []
        frame_id = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame_detections = self.detect_frame(frame, frame_id)
            all_detections.append(frame_detections)

            if output_callback:
                output_callback(frame_detections)

            frame_id += 1
            if max_frames and frame_id >= max_frames:
                break

        cap.release()
        logger.info(f"Detection complete — {frame_id} frames processed")
        return all_detections
