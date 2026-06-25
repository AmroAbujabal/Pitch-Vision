"""
metrics/formation.py

Formation detection stub.

Full implementation would:
1. Collect average pitch positions for all outfield players per team.
2. Sort by y-axis (depth from goal) to identify defensive / midfield / attacking lines.
3. Count players per line and return a formation string e.g. "4-3-3".

This requires:
- Reliable team assignment (home / away) for all confirmed tracks.
- A full-pitch view — single-camera footage covering only one half yields
  incomplete line counts.
- Minimum ~5 confirmed outfield players per team for a meaningful label.

TODO: implement once team colour classification is stable and a full-pitch
      (or two-camera) dataset is available.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tracking.types import TrackedFrame


def detect_formation(
    tracked_frames: list["TrackedFrame"],
    team: str = "home",
    min_players: int = 5,
) -> str:
    """
    Detect the formation for *team* across *tracked_frames*.

    Returns a formation string (e.g. "4-3-3") or "unknown" when detection
    is not possible (too few players, single-camera partial view, etc.).
    """
    # TODO: cluster mean positions → sort by depth → count lines
    return "unknown"
