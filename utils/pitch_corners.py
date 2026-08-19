"""
utils/pitch_corners.py

Validity of a set of manually annotated pitch corners.

Deliberately free of cv2 and numpy so the API can import it: the production
image installs requirements-ci.txt, which has no opencv, and
`utils/homography.py` imports cv2 at module scope.

`dashboard/lib/corners.ts` holds the same checks for the picker, so a coach
hears about a bad quad while they can still fix it. Two languages either side of
the wire means two implementations; keep them in step.
"""

from __future__ import annotations

from typing import Optional, Sequence

Corner = Sequence[float]

# Below this the quad is a mis-click, not a pitch. Video pixels squared.
MIN_AREA_PX = 10_000.0

# Cross products under this are treated as collinear.
COLLINEAR_EPS = 1e-6

_ORDER = (
    "Order them TL -> TR -> BR -> BL: the frame's top-left corner first, "
    "then clockwise."
)


def corner_problem(corners: Sequence[Corner]) -> Optional[str]:
    """
    Why these four corners cannot be used, or None if they can.

    `PitchHomography` maps corner 0 to pitch (0, 0), 1 to (105, 0), 2 to
    (105, 68) and 3 to (0, 68). Those four assignments are the whole contract:
    any other arrangement of the same four points still solves — cv2 fits a
    perfectly good homography and nothing downstream raises — it just describes
    a different pitch than the one on camera. So the order has to be checked
    here, since it cannot be detected later.

    Two independent things can be wrong, and each has to be tested separately:

    - **Which way round the quad is walked.** All four cross products come out
      positive for a clockwise walk in y-down pixels. Anticlockwise
      (BL -> BR -> TR -> TL) makes them all negative and mirrors pitch *width*:
      the left wing's heatmap appears on the right. Mixed signs mean a
      self-crossing bowtie, and a zero means three points on a line.

    - **Which corner is first.** Winding says nothing about that, and the three
      wrong rotations are all clockwise, so they pass the test above while
      describing quite different pitches. The 180° rotation
      (BR -> BL -> TL -> TR) mirrors *length*: x=0 lands on the far goal and a
      4-2-3-1 is reported as 1-3-2-4. The two 90° rotations transpose the axes
      entirely, laying the 105 m goal-to-goal axis across the frame's vertical
      extent, so formation clustering reads the near-far touchline direction as
      depth and the shape collapses. Pinned by checking the corners sit where
      their names say: the first two along the top of the frame, left then
      right, and the last two along the bottom, right then left.

    That frame-position test assumes the touchline camera this project is built
    for (see CLAUDE.md, "Input Assumption"). The convention it enforces is
    already baked in elsewhere — `home_defends_end="low"` is defined as the goal
    on the *left of frame* — so it narrows nothing that worked before.
    """
    if len(corners) != 4:
        return f"Need exactly 4 pitch corners. {_ORDER}"

    # Match.pitch_corners is a free-form JSON column, so a hand-edited or
    # pre-API row can hold a corner that is not a point at all. Checked before
    # any indexing: an IndexError here would escape callers that reasonably
    # expect this function to answer rather than raise.
    for corner in corners:
        if len(corner) != 2:
            return "Each pitch corner needs exactly an x and a y."

    crosses = [
        _cross(corners[i], corners[(i + 1) % 4], corners[(i + 2) % 4])
        for i in range(4)
    ]

    if any(abs(c) < COLLINEAR_EPS for c in crosses):
        return "Those pitch corners are collinear."

    if not all(c > 0 for c in crosses):
        return f"Those pitch corners are out of order. {_ORDER}"

    tl, tr, br, bl = corners
    if not (tl[0] < tr[0] and bl[0] < br[0] and tl[1] < bl[1] and tr[1] < br[1]):
        return f"Those pitch corners start from the wrong corner. {_ORDER}"

    if _area(corners) < MIN_AREA_PX:
        return "That corner quad is too small to be a pitch."

    return None


def _cross(a: Corner, b: Corner, c: Corner) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _area(corners: Sequence[Corner]) -> float:
    """Shoelace area of the quad, in square pixels."""
    total = 0.0
    for i in range(4):
        a, b = corners[i], corners[(i + 1) % 4]
        total += a[0] * b[1] - b[0] * a[1]
    return abs(total) / 2.0
