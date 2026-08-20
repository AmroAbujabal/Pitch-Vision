"""
metrics/formation.py

Formation detection from tracked player positions.

Detecting a formation requires knowing which way the team attacks: a shape of
[four clustered players] + [one isolated player] is mirror-identical whether the
lone player is the goalkeeper or a lone striker. Position data alone cannot break
that symmetry, so the attacking direction — the team's own-goal end along the
depth (x) axis — must be supplied by the caller (from pitch homography / goal
coordinates). When it is unknown, detection is declined ("unknown") rather than
guessed, because a confidently-wrong formation is worse than none for a coach.

Pitch coordinates follow the project convention: x = length (goal-to-goal,
0–105 m), y = width (0–68 m). Depth is therefore x.

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

Teams change ends at half-time, so the own-goal end is a property of *when* an
observation was made, not of the match. Pass half_time_frame and each position
is measured from the goal that team was actually defending at the time; without
it the whole video is treated as one direction, and a full match reports a
blend of the true shape and its mirror.
"""

from __future__ import annotations

import numpy as np
from typing import Optional, TYPE_CHECKING

from config.settings import settings

if TYPE_CHECKING:
    from tracking.types import Track, TrackedFrame


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
    half_time_frame: Optional[int] = None,
    min_players: int = 5,
) -> str:
    """
    Detect the formation for *team* across *tracked_frames*.

    own_goal_end: which end of the depth (x) axis holds the team's own goal at
        kick-off — "low" (own goal near x=0) or "high" (own goal near max x).
        Required: when None (direction unknown) the result is "unknown", by
        design.
    half_time_frame: the frame at which the teams change ends. Observations at
        or after it are oriented to the opposite goal. None means the whole
        video was played in one direction, which is what a single half is and
        what every caller did before this existed — it is never inferred,
        because a wrong split re-introduces the mirror it exists to remove.
    min_players: minimum confirmed tracks with position data (goalkeeper
        included) needed to attempt a label.

    Returns a formation string (e.g. "4-3-3") or "unknown".
    """
    if own_goal_end not in ("low", "high"):
        return "unknown"

    depths = _mean_depths(tracked_frames, team, own_goal_end, half_time_frame)
    if len(depths) < min_players or len(depths) < 2:
        return "unknown"

    outfield = _drop_goalkeeper(np.sort(depths))
    if not outfield.size:
        return "unknown"

    lines = _cluster_lines(outfield, LINE_TOLERANCE_M)
    return "-".join(str(n) for n in lines)


_OPPOSITE_END = {"low": "high", "high": "low"}


def _mean_depths(
    tracked_frames: list["TrackedFrame"],
    team: str,
    own_goal_end: str,
    half_time_frame: Optional[int],
) -> np.ndarray:
    """Mean distance from the own goal per confirmed track of *team*, unsorted.

    Every TrackedFrame holds references to the same live Track objects, so each
    track is read once rather than re-summed per frame. pitch_history is the
    real per-frame record and gives a true match average; pitch_pos is only the
    latest position, used as a fallback for tracks with no history.

    That "read once" assumes the tracker's shape — one Track object shared
    across frames, carrying its own history. Frames built from independent
    per-frame snapshots instead (a distinct Track per frame, no history) yield
    the first frame's positions, not an average.
    """
    depths: dict[int, float] = {}

    for frame in tracked_frames:
        for track in frame.confirmed_tracks:
            if track.team != team or track.track_id in depths:
                continue
            observations = _distances_from_own_goal(
                track, own_goal_end, half_time_frame
            )
            if observations:
                depths[track.track_id] = float(np.mean(observations))

    return np.array(list(depths.values()), dtype=float)


def _distances_from_own_goal(
    track: "Track",
    own_goal_end: str,
    half_time_frame: Optional[int],
) -> list[float]:
    """Each of *track*'s observed depths, as a distance from the goal its team
    was defending at the moment it was observed.

    Orienting per observation rather than per match is what makes the two
    halves comparable: they are measured from opposite physical goals but end
    up on one scale, so the mean over the whole match is meaningful.

    The conversion is absolute (`pitch_length - x`), not a flip about the
    deepest player seen. A relative flip is fine for a single direction — every
    downstream read is a difference — but two halves flipped about two
    different anchors are not on a common scale.

    frame_history is index-aligned with pitch_history: the tracker appends to
    bbox_history and frame_history together, and run_pipeline builds
    pitch_history one-for-one from bbox_history. An observation with no frame
    (a hand-built track, or the single-position fallback) cannot be attributed
    to a half and takes the first half's direction.
    """
    if not track.pitch_history:
        if track.pitch_pos is not None:
            return [_distance(float(track.pitch_pos[0]), own_goal_end)]
        return []

    frames = track.frame_history
    distances = []
    for i, pos in enumerate(track.pitch_history):
        frame_id = frames[i] if i < len(frames) else None
        end = _end_at(own_goal_end, half_time_frame, frame_id)
        distances.append(_distance(float(pos[0]), end))
    return distances


def _end_at(
    first_half_end: str,
    half_time_frame: Optional[int],
    frame_id: Optional[int],
) -> str:
    """Which end the team defended when *frame_id* was observed."""
    if half_time_frame is None or frame_id is None or frame_id < half_time_frame:
        return first_half_end
    return _OPPOSITE_END[first_half_end]


def _distance(x: float, own_goal_end: str) -> float:
    """Along-pitch distance from the own goal, so 0 is the own goal line."""
    return x if own_goal_end == "low" else settings.pitch_length - x


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
