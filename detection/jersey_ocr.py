"""
detection/jersey_ocr.py

Extracts jersey numbers from player crops using PaddleOCR.
Focuses on the upper-body region where numbers appear.
"""

from __future__ import annotations

import re
import cv2
import numpy as np
from typing import Optional
from loguru import logger

from config.settings import settings


class JerseyOCR:
    """
    Extracts jersey numbers from player bounding box crops.
    Uses PaddleOCR with digit-focused post-processing.
    """

    def __init__(self):
        self._ocr = None

    def _get_ocr(self):
        """Lazy-load PaddleOCR to avoid slow startup when not needed."""
        if self._ocr is None:
            try:
                from paddleocr import PaddleOCR
                self._ocr = PaddleOCR(
                    use_angle_cls=True,
                    lang="en",
                    show_log=False,
                )
                logger.info("PaddleOCR loaded for jersey number extraction")
            except ImportError:
                logger.warning("PaddleOCR not installed — jersey OCR disabled")
        return self._ocr

    def _preprocess_crop(self, crop: np.ndarray) -> np.ndarray:
        """
        Isolate the jersey number region and enhance contrast.
        Jersey numbers typically appear in the top 55% of the player crop.
        """
        h, w = crop.shape[:2]
        jersey_region = crop[int(h * 0.1): int(h * 0.55), :]

        # Upscale for better OCR accuracy on small crops
        scale = max(1.0, 80.0 / jersey_region.shape[0])
        resized = cv2.resize(
            jersey_region,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC,
        )

        # Increase contrast
        lab = cv2.cvtColor(resized, cv2.COLOR_BGR2LAB)
        l_ch, a_ch, b_ch = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
        l_ch = clahe.apply(l_ch)
        enhanced = cv2.merge([l_ch, a_ch, b_ch])
        return cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)

    def _parse_number(self, text: str) -> Optional[int]:
        """
        Extract a valid jersey number (1–99) from raw OCR text.
        Returns None if no valid number found.
        """
        digits = re.findall(r"\d+", text.strip())
        for d in digits:
            num = int(d)
            if 1 <= num <= 99:
                return num
        return None

    def extract(self, crop: np.ndarray) -> tuple[Optional[int], float]:
        """
        Extract jersey number from a player crop.

        Returns:
            (jersey_number, confidence) — number is None if not detected
        """
        ocr = self._get_ocr()
        if ocr is None or crop.size == 0:
            return None, 0.0

        preprocessed = self._preprocess_crop(crop)

        try:
            results = ocr.ocr(preprocessed, cls=True)
        except Exception as e:
            logger.debug(f"OCR error: {e}")
            return None, 0.0

        if not results or not results[0]:
            return None, 0.0

        best_number = None
        best_conf = 0.0

        for line in results[0]:
            if line is None:
                continue
            text_info = line[1]            # (text, confidence)
            text, conf = text_info[0], text_info[1]

            if conf < settings.jersey_ocr_conf:
                continue

            number = self._parse_number(text)
            if number is not None and conf > best_conf:
                best_number = number
                best_conf = conf

        return best_number, best_conf

    def batch_extract(
        self, crops: list[np.ndarray]
    ) -> list[tuple[Optional[int], float]]:
        """Extract jersey numbers from a batch of crops."""
        return [self.extract(crop) for crop in crops]
