"""
metrics/formation.py

Formation detection from tracked player positions.

Detecting a formation requires knowing which way the team attacks: a shape of
[four clustered players] + [one isolated player] is mirror-identical whether the
lone player is the goalkeeper or a lone striker. Position data alone cannot break
that symmetry, so the attacking direction — the team's own-goal end along the
depth (y) axis — must be supplied by the caller (from pitch homography / goal
coordinates). When it is unknown, detection is declined ("unknown") rather than
guessed, because a confidently-wrong formation is worse than none for a coach.

Given the own-goal end, detection is:
1. Aggregate each confirmed track's mean depth for the target team.
2. Orient depth so the own goal is at 0 and attackers are deepest up-pitch.
3. If the nearest player is isolated behind the next line by a keeper-like gap,
   drop it as the goalkeeper; otherwise keep everyone (keeper off-camera).
4. Gap-cluster the remaining players into lines and format the counts
   defence -> attack (e.g. "4-3-3").

Known limitations (single fixed camera): a partial-pitch view yields incomplete
line counts, and a keeper standing level with the back line is not removed.
Returns "unknown" when direction is unknown or there is too little data.
"""

from __future__ import annotations

import numpy as np
from collections import defaultdict
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from tracking.types import TrackedFrame


# Depth gap (metres) above which two adjacent players are treated as separate
# lines. Sized to sit above a normal intra-line stagger (attacking full-backs,
# a striker drifting off the wingers) yet below a typical inter-line spacing.
LINE_TOLERANCE_M = 12.0

# Minimum gap (metres) between the deepest player and the next line for that
# player to be classed as the goalkeeper rather than a deep defender.
GK_ISOLATION_M = 12.0


def detect_formation(
    tracked_frames: list["TrackedFrame"],
    team: str = "home",
    *,
    own_goal_end: Optional[str] = None,
    min_players: int = 5,
) -> str:
    """
    Detect the formation for *team* across *tracked_frames*.

    own_goal_end: which end of the depth (y) axis holds the team's own goal —
        "low" (own goal near y=0) or "high" (own goal near max y). Required:
        when None (direction unknown) the result is "unknown", by design.
    min_players: minimum confirmed tracks with position data (goalkeeper
        included) needed to attempt a label.

    Returns a formation string (e.g. "4-3-3") or "unknown".
    """
    if own_goal_end not in ("low", "high"):
        return "unknown"

    depths = _mean_depths(tracked_frames, team)
    if len(depths) < min_players or len(depths) < 2:
        return "unknown"

    oriented = _orient_to_own_goal(depths, own_goal_end)
    outfield = _drop_goalkeeper(oriented)
    if not outfield.size:
        return "unknown"

    lines = _cluster_lines(outfield, LINE_TOLERANCE_M)
    return "-".join(str(n) for n in lines)


def _mean_depths(tracked_frames: list["TrackedFrame"], team: str) -> np.ndarray:
    """Mean along-pitch depth (y) per confirmed track of *team*, unsorted."""
    sums: dict[int, float] = defaultdict(float)
    counts: dict[int, int] = defaultdict(int)

    for frame in tracked_frames:
        for track in frame.confirmed_tracks:
            if track.team != team or track.pitch_pos is None:
                continue
            sums[track.track_id] += float(track.pitch_pos[1])  # y == depth axis
            counts[track.track_id] += 1

    depths = [sums[tid] / counts[tid] for tid in sums]
    return np.array(depths, dtype=float)


def _orient_to_own_goal(depths: np.ndarray, own_goal_end: str) -> np.ndarray:
    """Return depths sorted ascending from the own goal (index 0 = deepest)."""
    s = np.sort(depths)
    if own_goal_end == "high":
        s = np.sort(s.max() - s)  # own goal was at the high-y end; flip
    return s


def _drop_goalkeeper(oriented: np.ndarray) -> np.ndarray:
    """Drop the deepest player only if it is isolated behind the next line by a
    keeper-like gap; otherwise the keeper is off-camera, so keep everyone."""
    if oriented.size >= 2 and (oriented[1] - oriented[0]) >= GK_ISOLATION_M:
        return oriented[1:]
    return oriented


def _cluster_lines(depths_sorted: np.ndarray, tolerance: float) -> list[int]:
    """Split depth-sorted outfielders into lines wherever the gap exceeds
    *tolerance*, returning the player count per line, defence -> attack."""
    lines: list[int] = [1]
    for prev, curr in zip(depths_sorted[:-1], depths_sorted[1:]):
        if curr - prev > tolerance:
            lines.append(1)
        else:
            lines[-1] += 1
    return lines
