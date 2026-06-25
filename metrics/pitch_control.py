"""
metrics/pitch_control.py

Computes frame-level pitch control for each player.
Based on the Spearman (2018) / Friends of Tracking model:
each player "controls" the zones they can reach before any opponent.

Output: a probability surface (grid) showing what fraction of the pitch
each team controls, plus per-player contribution scores.
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass
from typing import Optional

from config.settings import settings
from tracking.types import Track
from utils.homography import PitchHomography


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

GRID_COLS = 50          # pitch divided into 50 x 32 cells
GRID_ROWS = 32
PLAYER_REACTION_TIME = 0.7    # seconds before a player starts moving
PLAYER_MAX_SPEED = 8.0        # m/s — max sprint speed
PLAYER_SIGMA = 10.0           # spatial uncertainty parameter (metres)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PitchControlFrame:
    """Pitch control output for a single frame."""
    frame_id: int

    # (GRID_ROWS, GRID_COLS) array — probability home team controls each cell
    home_surface: np.ndarray

    # Per-player contribution: track_id → mean control value in their zone
    player_contributions: dict[int, float]

    @property
    def away_surface(self) -> np.ndarray:
        return 1.0 - self.home_surface

    @property
    def home_control_pct(self) -> float:
        return float(self.home_surface.mean())

    @property
    def away_control_pct(self) -> float:
        return float(self.away_surface.mean())


# ---------------------------------------------------------------------------
# Coordinate utilities
# ---------------------------------------------------------------------------

def pixel_to_pitch(
    pixel_pos: np.ndarray,
    frame_w: int = settings.frame_width,
    frame_h: int = settings.frame_height,
    pitch_l: float = settings.pitch_length,
    pitch_w: float = settings.pitch_width,
) -> np.ndarray:
    """Convert pixel (x, y) to pitch metres (x, y)."""
    return np.array([
        pixel_pos[0] / frame_w * pitch_l,
        pixel_pos[1] / frame_h * pitch_w,
    ])


def build_pitch_grid() -> tuple[np.ndarray, np.ndarray]:
    """
    Build a meshgrid of pitch cell centres in metres.
    Returns (grid_x, grid_y) each of shape (GRID_ROWS, GRID_COLS).
    """
    x_coords = np.linspace(0, settings.pitch_length, GRID_COLS)
    y_coords = np.linspace(0, settings.pitch_width, GRID_ROWS)
    return np.meshgrid(x_coords, y_coords)


GRID_X, GRID_Y = build_pitch_grid()
GRID_POINTS = np.stack([GRID_X.ravel(), GRID_Y.ravel()], axis=1)  # (N_cells, 2)


# ---------------------------------------------------------------------------
# Player influence model
# ---------------------------------------------------------------------------

def player_influence(
    player_pos: np.ndarray,    # (2,) pitch coords in metres
    player_vel: Optional[np.ndarray],  # (2,) velocity in m/s, or None
    grid_points: np.ndarray = GRID_POINTS,
) -> np.ndarray:
    """
    Compute this player's influence over every grid cell.

    Uses a 2D Gaussian centred at the player's projected position
    (reaction_time * velocity ahead of current position).
    Sigma expands with distance to capture uncertainty.

    Returns array of shape (N_cells,) with values in [0, 1].
    """
    if player_vel is not None and np.linalg.norm(player_vel) > 0.1:
        projected = player_pos + player_vel * PLAYER_REACTION_TIME
    else:
        projected = player_pos.copy()

    # Clip to pitch bounds
    projected[0] = np.clip(projected[0], 0, settings.pitch_length)
    projected[1] = np.clip(projected[1], 0, settings.pitch_width)

    # Distance from projected position to each grid cell
    diff = grid_points - projected  # (N_cells, 2)
    dist_sq = np.sum(diff ** 2, axis=1)

    # Gaussian influence
    influence = np.exp(-dist_sq / (2 * PLAYER_SIGMA ** 2))
    return influence


# ---------------------------------------------------------------------------
# Main pitch control computation
# ---------------------------------------------------------------------------

def compute_pitch_control(
    frame_id: int,
    home_tracks: list[Track],
    away_tracks: list[Track],
    homography: Optional[PitchHomography] = None,
) -> PitchControlFrame:
    """
    Compute pitch control for a single frame.

    Args:
        frame_id:     frame index
        home_tracks:  confirmed tracks for home team
        away_tracks:  confirmed tracks for away team

    Returns:
        PitchControlFrame with control surface and player contributions
    """
    n_cells = len(GRID_POINTS)

    home_influence = np.zeros(n_cells)
    away_influence = np.zeros(n_cells)
    player_contributions: dict[int, float] = {}

    def get_pitch_pos(track: Track) -> Optional[np.ndarray]:
        """Get pitch position in metres from track's pixel bbox center."""
        if track.pitch_pos is not None:
            return track.pitch_pos
        center_px = track.center
        if homography is not None:
            return homography.pixel_to_pitch(center_px)
        return pixel_to_pitch(center_px)

    def get_pitch_vel(track: Track) -> Optional[np.ndarray]:
        """Get velocity in m/s from pixel velocity history."""
        vel_px = track.velocity
        if vel_px is None:
            return None
        # Convert pixels/frame to m/s
        fps = settings.default_fps
        vel_m_per_s = np.array([
            vel_px[0] / settings.frame_width * settings.pitch_length * fps,
            vel_px[1] / settings.frame_height * settings.pitch_width * fps,
        ])
        speed = np.linalg.norm(vel_m_per_s)
        if speed > PLAYER_MAX_SPEED:
            vel_m_per_s = vel_m_per_s / speed * PLAYER_MAX_SPEED
        return vel_m_per_s

    for track in home_tracks:
        pos = get_pitch_pos(track)
        if pos is None:
            continue
        vel = get_pitch_vel(track)
        inf = player_influence(pos, vel)
        home_influence += inf
        player_contributions[track.track_id] = float(inf.mean())

    for track in away_tracks:
        pos = get_pitch_pos(track)
        if pos is None:
            continue
        vel = get_pitch_vel(track)
        inf = player_influence(pos, vel)
        away_influence += inf
        player_contributions[track.track_id] = float(inf.mean())

    # Probability home team controls each cell
    total = home_influence + away_influence
    home_prob = np.where(total > 1e-6, home_influence / total, 0.5)

    home_surface = home_prob.reshape(GRID_ROWS, GRID_COLS)

    return PitchControlFrame(
        frame_id=frame_id,
        home_surface=home_surface,
        player_contributions=player_contributions,
    )


def compute_dangerous_zone_occupancy(
    tracks: list[Track],
    home_attack_direction: str = "right",  # "left" | "right"
) -> dict[int, float]:
    """
    Score each player by how much time they spend in high-xT zones.
    High-xT zones = final third + penalty area vicinity.

    Returns dict: track_id → occupancy score [0, 1]
    """
    pitch_l = settings.pitch_length

    if home_attack_direction == "right":
        danger_x_min = pitch_l * 0.67    # final third
    else:
        danger_x_min = 0.0
        danger_x_max_left = pitch_l * 0.33

    scores: dict[int, float] = {}

    for track in tracks:
        if not track.pitch_history:
            scores[track.track_id] = 0.0
            continue

        positions = np.array(track.pitch_history)
        total = len(positions)

        if home_attack_direction == "right":
            in_danger = np.sum(positions[:, 0] >= danger_x_min)
        else:
            in_danger = np.sum(positions[:, 0] <= danger_x_max_left)

        scores[track.track_id] = float(in_danger / total) if total > 0 else 0.0

    return scores
