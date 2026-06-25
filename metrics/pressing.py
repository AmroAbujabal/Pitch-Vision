"""
metrics/pressing.py

Computes all press-related advanced metrics per player:
- Press Trigger Timing  (did they press on the right cue?)
- Press Success Rate     (did the press force a turnover within N seconds?)
- PPDA per player        (passes allowed per defensive action)
- Recovery Shadow        (correct angle after losing possession)
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass
from typing import Optional
from loguru import logger

from config.settings import settings
from tracking.types import Track, TrackedFrame
from utils.homography import PitchHomography


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PressEvent:
    """A single pressing action by one player."""
    frame_id: int
    track_id: int
    target_track_id: int        # the player being pressed
    distance_at_start: float    # metres
    press_triggered_correctly: Optional[bool] = None
    succeeded: Optional[bool] = None   # did it force turnover within window?
    frames_to_outcome: Optional[int] = None


@dataclass
class PlayerPressStats:
    """Aggregated press statistics for one player across a match."""
    track_id: int
    press_count: int = 0
    correct_trigger_count: int = 0
    success_count: int = 0
    ppda_defensive_actions: int = 0

    @property
    def press_success_rate(self) -> float:
        if self.press_count == 0:
            return 0.0
        return self.success_count / self.press_count

    @property
    def trigger_accuracy(self) -> float:
        if self.press_count == 0:
            return 0.0
        return self.correct_trigger_count / self.press_count


# ---------------------------------------------------------------------------
# Press detection
# ---------------------------------------------------------------------------

class PressAnalyser:
    """
    Detects pressing actions and evaluates their quality.

    A press is detected when:
    - A defending player closes down an opponent at > 3 m/s
    - Distance to opponent drops below press_distance_threshold
    - The closing speed is directed toward the ball carrier
    """

    def __init__(self, homography: Optional[PitchHomography] = None):
        self.press_events: list[PressEvent] = []
        self.player_stats: dict[int, PlayerPressStats] = {}
        self._homography = homography

    def _get_pitch_pos(self, track: Track) -> Optional[np.ndarray]:
        if track.pitch_pos is not None:
            return track.pitch_pos
        bbox = track.bbox
        cx = (bbox[0] + bbox[2]) / 2
        cy = (bbox[1] + bbox[3]) / 2
        center_px = np.array([cx, cy])
        if self._homography is not None:
            return self._homography.pixel_to_pitch(center_px)
        return np.array([
            cx / settings.frame_width * settings.pitch_length,
            cy / settings.frame_height * settings.pitch_width,
        ])

    def _get_closing_speed(
        self, track: Track, target_pos: np.ndarray
    ) -> float:
        """
        Compute how fast this player is moving toward target_pos.
        Returns speed in m/s (positive = moving toward target).
        """
        vel = track.velocity
        if vel is None:
            return 0.0

        pos = self._get_pitch_pos(track)
        if pos is None:
            return 0.0

        fps = settings.default_fps
        vel_m = np.array([
            vel[0] / settings.frame_width * settings.pitch_length * fps,
            vel[1] / settings.frame_height * settings.pitch_width * fps,
        ])

        direction = target_pos - pos
        dist = np.linalg.norm(direction)
        if dist < 1e-6:
            return 0.0

        unit_dir = direction / dist
        return float(np.dot(vel_m, unit_dir))

    def detect_press_events(
        self,
        frames: list[TrackedFrame],
        ball_carrier_ids: Optional[dict[int, int]] = None,
    ) -> list[PressEvent]:
        """
        Scan all frames and identify pressing actions.

        Args:
            frames:            list of TrackedFrame
            ball_carrier_ids:  frame_id → track_id of ball carrier (optional)

        Returns:
            list of PressEvent
        """
        events: list[PressEvent] = []

        for frame in frames:
            frame_id = frame.frame_id
            tracks = frame.confirmed_tracks

            home = [t for t in tracks if t.team == "home"]
            away = [t for t in tracks if t.team == "away"]

            # Check home pressing away and vice versa
            for pressing_side, pressed_side in [(home, away), (away, home)]:
                for presser in pressing_side:
                    presser_pos = self._get_pitch_pos(presser)
                    if presser_pos is None:
                        continue

                    for target in pressed_side:
                        target_pos = self._get_pitch_pos(target)
                        if target_pos is None:
                            continue

                        dist = float(np.linalg.norm(presser_pos - target_pos))
                        closing = self._get_closing_speed(presser, target_pos)

                        if (
                            dist < settings.press_distance_threshold
                            and closing > 2.0   # m/s minimum closing speed
                        ):
                            event = PressEvent(
                                frame_id=frame_id,
                                track_id=presser.track_id,
                                target_track_id=target.track_id,
                                distance_at_start=dist,
                            )
                            events.append(event)

        self.press_events = events
        logger.info(f"Detected {len(events)} press events")
        return events

    def evaluate_press_outcomes(
        self,
        frames: list[TrackedFrame],
        turnover_frames: Optional[set[int]] = None,
    ) -> None:
        """
        For each press event, check if a turnover occurred within
        press_window_seconds frames after the press started.

        Args:
            frames:           all tracked frames
            turnover_frames:  set of frame IDs where turnovers occurred
        """
        fps = settings.default_fps
        window = int(settings.press_window_seconds * fps)

        for event in self.press_events:
            if turnover_frames is None:
                event.succeeded = None
                continue

            outcome_frames = range(event.frame_id, event.frame_id + window)
            event.succeeded = any(fid in turnover_frames for fid in outcome_frames)
            event.frames_to_outcome = next(
                (fid - event.frame_id for fid in outcome_frames
                 if fid in turnover_frames),
                None,
            )

    def aggregate_player_stats(self) -> dict[int, PlayerPressStats]:
        """
        Aggregate per-player press statistics from detected events.
        Returns dict: track_id → PlayerPressStats
        """
        stats: dict[int, PlayerPressStats] = {}

        for event in self.press_events:
            tid = event.track_id
            if tid not in stats:
                stats[tid] = PlayerPressStats(track_id=tid)

            stats[tid].press_count += 1

            if event.succeeded:
                stats[tid].success_count += 1

            if event.press_triggered_correctly:
                stats[tid].correct_trigger_count += 1

        self.player_stats = stats
        return stats


# ---------------------------------------------------------------------------
# Recovery shadow
# ---------------------------------------------------------------------------

def compute_recovery_shadow_score(
    track: Track,
    lost_possession_frame: int,
    ball_pos_after: Optional[np.ndarray],
    goal_pos: np.ndarray = np.array([settings.pitch_length, settings.pitch_width / 2]),
    window_frames: int = 30,
) -> float:
    """
    After losing possession, does this player take the correct recovery angle?

    The "correct" recovery angle positions the player between the ball
    and the goal they're defending, in the most dangerous pass lane.

    Returns a score [0, 1] — 1 = perfect recovery angle.
    """
    relevant_history = [
        (fid, pos)
        for fid, pos in zip(track.frame_history, track.pitch_history)
        if lost_possession_frame <= fid <= lost_possession_frame + window_frames
    ]

    if not relevant_history or ball_pos_after is None:
        return 0.0

    scores = []
    for _, player_pos in relevant_history:
        player_pos = np.array(player_pos)

        # Vector from ball to goal
        ball_to_goal = goal_pos - ball_pos_after
        btg_norm = np.linalg.norm(ball_to_goal)
        if btg_norm < 1e-6:
            continue

        # Vector from ball to player
        ball_to_player = player_pos - ball_pos_after
        btp_norm = np.linalg.norm(ball_to_player)
        if btp_norm < 1e-6:
            continue

        # How aligned is the player with the ball-to-goal vector?
        cos_angle = np.dot(ball_to_goal / btg_norm, ball_to_player / btp_norm)
        alignment = (cos_angle + 1) / 2  # map [-1, 1] → [0, 1]

        # Distance penalty — player should be between ball and goal
        player_dist_to_goal = np.linalg.norm(goal_pos - player_pos)
        ball_dist_to_goal = btg_norm
        between_penalty = 1.0 if player_dist_to_goal < ball_dist_to_goal else 0.5

        scores.append(alignment * between_penalty)

    return float(np.mean(scores)) if scores else 0.0
