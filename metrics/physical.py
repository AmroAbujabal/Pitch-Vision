"""
metrics/physical.py

Computes per-player physical performance metrics from pitch-coordinate
position histories.

All functions are pure — no DB, no I/O, no GPU.
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass

from config.settings import settings


# Speed zone thresholds (m/s)
ZONE_WALK    = 2.0
ZONE_JOG     = 4.0
ZONE_RUN     = 7.0
# anything >= ZONE_RUN is sprint


@dataclass
class PhysicalMetrics:
    """Physical performance metrics for one player in one match."""
    track_id: int
    top_speed_ms: float
    avg_speed_ms: float
    distance_covered_m: float
    hi_run_count: int      # distinct bouts above high_intensity_speed threshold
    sprint_count: int      # distinct bouts above sprint_speed threshold
    speed_zones: dict = None  # {"walk_pct": float, "jog_pct": float, "run_pct": float, "sprint_pct": float}


def compute_physical_metrics(
    track_id: int,
    pitch_positions: np.ndarray,   # (N, 2) in pitch metres
    fps: float = settings.default_fps,
    hi_speed_threshold: float = settings.high_intensity_speed,
    sprint_threshold: float = settings.sprint_speed,
) -> PhysicalMetrics:
    """
    Compute physical metrics from a sequence of pitch-coordinate positions.

    Args:
        track_id:           identifier for the player track
        pitch_positions:    (N, 2) array of (x, y) positions in metres
        fps:                frames per second of the source video
        hi_speed_threshold: m/s — minimum speed for a high-intensity run
        sprint_threshold:   m/s — minimum speed for a sprint

    Returns:
        PhysicalMetrics dataclass
    """
    n = len(pitch_positions)

    _empty_zones: dict = {
        "walk_pct": 0.0, "jog_pct": 0.0, "run_pct": 0.0, "sprint_pct": 0.0
    }

    if n < 2:
        return PhysicalMetrics(
            track_id=track_id,
            top_speed_ms=0.0,
            avg_speed_ms=0.0,
            distance_covered_m=0.0,
            hi_run_count=0,
            sprint_count=0,
            speed_zones=_empty_zones,
        )

    # Frame-to-frame distances in metres
    deltas = np.linalg.norm(np.diff(pitch_positions, axis=0), axis=1)  # (N-1,)

    # Speed at each interval in m/s
    speeds = deltas * fps  # (N-1,)

    distance   = float(deltas.sum())
    top_speed  = float(speeds.max())
    avg_speed  = float(speeds.mean())

    hi_run_count = _count_bouts(speeds, hi_speed_threshold)
    sprint_count  = _count_bouts(speeds, sprint_threshold)
    speed_zones   = _compute_speed_zones(speeds)

    return PhysicalMetrics(
        track_id=track_id,
        top_speed_ms=top_speed,
        avg_speed_ms=avg_speed,
        distance_covered_m=distance,
        hi_run_count=hi_run_count,
        sprint_count=sprint_count,
        speed_zones=speed_zones,
    )


def _compute_speed_zones(speeds: np.ndarray) -> dict:
    """
    Classify each speed sample into a zone and return the fraction of time
    spent in each zone.

    Zones (m/s):
        walk   < 2.0
        jog    2.0 – 4.0
        run    4.0 – 7.0
        sprint ≥ 7.0
    """
    n = len(speeds)
    if n == 0:
        return {"walk_pct": 0.0, "jog_pct": 0.0, "run_pct": 0.0, "sprint_pct": 0.0}

    walk   = float(np.sum(speeds < ZONE_WALK))
    jog    = float(np.sum((speeds >= ZONE_WALK)  & (speeds < ZONE_JOG)))
    run    = float(np.sum((speeds >= ZONE_JOG)   & (speeds < ZONE_RUN)))
    sprint = float(np.sum(speeds >= ZONE_RUN))

    return {
        "walk_pct":   round(walk   / n, 4),
        "jog_pct":    round(jog    / n, 4),
        "run_pct":    round(run    / n, 4),
        "sprint_pct": round(sprint / n, 4),
    }


def _count_bouts(speeds: np.ndarray, threshold: float) -> int:
    """
    Count the number of distinct contiguous periods where speed > threshold.

    A new bout begins when speed crosses from ≤ threshold to > threshold.
    """
    above = speeds > threshold
    # Rising edges: False → True transitions
    bouts = int(np.sum(np.diff(above.astype(np.int8)) == 1))
    # If the sequence starts already above threshold, count that as a bout too
    if len(above) > 0 and above[0]:
        bouts += 1
    return bouts
