# Half-Time End Swap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop a full match's formation from being computed with one half's positions mirrored, by letting the coach mark half-time and orienting every position to the goal its team was actually defending at that moment.

**Architecture:** One nullable column (`Match.half_time_seconds`) threaded migration → API → dashboard picker → `run_pipeline`. `metrics/formation.py` changes from a per-match orientation anchored on the deepest observed player to a per-observation absolute conversion (`x` or `pitch_length - x`), which puts both halves on a common scale so the existing whole-match output keeps its meaning. Attribution to a half is a filter on `Track.frame_history`, which is index-aligned with `pitch_history` — no tracker changes.

**Tech Stack:** Python 3.11 (`/usr/local/bin/python3.11`), SQLAlchemy 2 + Alembic, FastAPI + Pydantic v2, numpy, pytest, ruff; Next.js 14 App Router + TypeScript + Tailwind, vitest.

**Spec:** `docs/superpowers/specs/2026-08-19-half-time-end-swap-design.md`

## Global Constraints

- Pitch coordinate convention: **x = length (goal-to-goal, 0–105 m), y = width (0–68 m). Depth is x.** Never re-derive this; it has been wrong twice.
- `half_time_seconds` is **NULL by default and never guessed**. NULL must reproduce today's behaviour byte for byte.
- Store **seconds**, convert to a frame **once**, in `run_pipeline`, where `fps` is resolved. `detect_formation` takes a frame and never learns about `fps`.
- Do **not** add test-only dependencies to `requirements-ci.txt` — `Dockerfile:16` installs it into the production image. Test deps go in `requirements-test.txt`.
- `metrics/formation.py` must stay free of cv2 and torch (it is imported by API-side tests); `config.settings` is fine.
- Run Python with `/usr/local/bin/python3.11` — there is no conda on this machine.
- Baseline before any change: **291 pytest / 41 vitest / ruff clean / tsc clean.**
- Commit after each task. Do not push; the session owner pushes at the end.

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `metrics/formation.py` | Per-observation orientation + half attribution (the whole behaviour change) | 1 |
| `tests/test_metrics/test_formation.py` | Straddling-track, boundary and mirror-demonstration tests | 1 |
| `database/models.py` | `Match.half_time_seconds` column | 2 |
| `alembic/versions/a4c7e912b6d3_add_half_time_to_match.py` | The migration | 2 |
| `api/routers/matches.py` | `MatchCalibration.half_time_seconds`, persisted by `set_calibration` | 3 |
| `tests/test_api/test_calibration.py` | Round-trip, NULL, and rejection tests | 3 |
| `scripts/run_pipeline.py` | `half_time_seconds` kwarg + CLI flag, seconds→frame, pass to `detect_formation` | 4 |
| `tasks/pipeline.py` | The commented-out `run(...)` call gains the argument | 4 |
| `tests/test_pipeline/test_positions.py` | Seconds→frame conversion tests | 4 |
| `dashboard/lib/half-time.ts` | Pure `mm:ss` ↔ seconds parsing (the part that fails silently) | 5 |
| `dashboard/lib/half-time.test.ts` | vitest for the parser | 5 |
| `dashboard/components/CalibratePicker.tsx` | The `mm:ss` input, sent by `save()` | 5 |

Task 1 is the whole correctness fix and is independently testable with no schema or wire change. Tasks 2–5 carry the value from the coach's screen to the detector. Do them in order: Task 3 imports nothing from Task 1, but Task 4 wires both together and should not run before either exists.

---

### Task 1: Per-observation orientation in `metrics/formation.py`

**Files:**
- Modify: `metrics/formation.py` (module docstring, `detect_formation`, `_mean_depths`; delete `_orient_to_own_goal`)
- Test: `tests/test_metrics/test_formation.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `detect_formation(tracked_frames, team="home", *, own_goal_end=None, half_time_frame: int | None = None, min_players=5) -> str`. Task 4 calls it with `half_time_frame`.

**Background the implementer needs:**

- `Track` (`tracking/types.py`) carries `pitch_history: list[np.ndarray]` and `frame_history: list[int]`. `tracker._new_track` and `_update_track` append `bbox_history` and `frame_history` together, and `run_pipeline` builds `pitch_history` one-for-one from `bbox_history`, so `pitch_history[i]` was observed at `frame_history[i]`.
- **The existing tests build tracks with `pitch_pos` or `pitch_history` and no `frame_history` at all.** Code that indexes `frame_history[i]` unguarded will `IndexError` across most of the existing 19 tests. An observation with no known frame belongs to the **first half** — that is the documented rule, not a workaround.
- `_orient_to_own_goal` currently flips with `s.max() - s`. `L - s` differs from it by the constant `L - max(s)`, and every downstream read (line clustering, the goalkeeper gap) is a difference, so **the existing 19 tests must pass unchanged**. If one fails, stop and report — that is a real finding about this reasoning, not a test to update.
- `scripts/run_pipeline.py` has its own `_OPPOSITE_END`, imported by `tests/test_pipeline/test_positions.py`. **Do not unify the two.** `metrics/` must not import from `scripts/`, and moving it would churn an unrelated test for a one-line dict.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_metrics/test_formation.py`:

```python
# ---------------------------------------------------------------------------
# Half-time end swap
# ---------------------------------------------------------------------------

def with_history(tracks: list, frames: list, mirror_from: int | None = None) -> list:
    """Give every track a pitch_history observed at *frames*.

    Positions come from each track's pitch_pos. When *mirror_from* is given,
    observations at or after that frame are mirrored along the length axis —
    which is exactly what a real second half looks like once the teams change
    ends, since the camera does not move.
    """
    for t in tracks:
        depth, lateral = t.pitch_pos
        history = []
        for f in frames:
            x = 105.0 - depth if mirror_from is not None and f >= mirror_from else depth
            history.append(np.array([x, lateral], dtype=float))
        t.pitch_history = history
        t.frame_history = list(frames)
    return tracks


class TestHalfTimeEndSwap:

    def test_swapped_second_half_is_corrected(self):
        """The teams change ends at frame 100. With the split declared, the
        4-4-2 is still a 4-4-2."""
        tracks = with_history(layout_442(), frames=[0, 50, 150, 199], mirror_from=100)
        assert detect_formation(
            frames_from(tracks), team="home",
            own_goal_end="low", half_time_frame=100,
        ) == "4-4-2"

    def test_without_the_split_the_same_match_is_wrong(self):
        """States the bug: the identical data, with no half-time mark, averages
        each player's two ends together and collapses the shape."""
        tracks = with_history(layout_442(), frames=[0, 50, 150, 199], mirror_from=100)
        assert detect_formation(
            frames_from(tracks), team="home", own_goal_end="low",
        ) != "4-4-2"

    def test_a_wrong_split_gives_a_wrong_answer(self):
        """The risk this feature takes on, stated as a test.

        A declared split is trusted. Positions that did not actually swap get
        their second half mirrored, which averages every player with their own
        mirror and collapses the shape. Nothing server-side can detect this —
        the only mitigation is that the coach types the mark while watching the
        video. Pinned so that a future "helpful" attempt to infer or correct
        the split has to argue with this test rather than pass silently.
        """
        tracks = with_history(layout_442(), frames=[0, 50, 150, 199])
        assert detect_formation(
            frames_from(tracks), team="home",
            own_goal_end="low", half_time_frame=100,
        ) != "4-4-2"

    def test_observation_on_the_boundary_is_second_half(self):
        """Off-by-one here is a silent half-swap, so the boundary is pinned.

        Every observation sits exactly on the split and is mirrored. Reading
        the boundary as second-half orients all of them correctly; reading it
        as first-half mirrors the whole match into 2-4-4.
        """
        tracks = with_history(layout_442(), frames=[100, 100, 100], mirror_from=100)
        assert detect_formation(
            frames_from(tracks), team="home",
            own_goal_end="low", half_time_frame=100,
        ) == "4-4-2"

    def test_away_team_swaps_the_other_way(self):
        """The away team starts at the high end and ends at the low one."""
        positions = [(105 - x, y) for (x, y) in [
            (5, 34),
            (22, 10), (22, 26), (22, 42), (22, 58),
            (52, 10), (52, 26), (52, 42), (52, 58),
            (80, 26), (80, 42),
        ]]
        tracks = with_history(
            make_team("away", positions), frames=[0, 150], mirror_from=100
        )
        assert detect_formation(
            frames_from(tracks), team="away",
            own_goal_end="high", half_time_frame=100,
        ) == "4-4-2"

    def test_observations_without_a_frame_are_first_half(self):
        """pitch_history with no frame_history cannot be attributed, so it
        takes the first half's direction — today's behaviour."""
        tracks = layout_442()
        for t in tracks:
            t.pitch_history = [np.asarray(t.pitch_pos, dtype=float)]
            t.frame_history = []
        assert detect_formation(
            frames_from(tracks), team="home",
            own_goal_end="low", half_time_frame=100,
        ) == "4-4-2"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/usr/local/bin/python3.11 -m pytest tests/test_metrics/test_formation.py -q`
Expected: FAIL — `TypeError: detect_formation() got an unexpected keyword argument 'half_time_frame'` on five of them, and `test_without_the_split_the_same_match_is_wrong` may already pass (it describes today's broken behaviour).

- [ ] **Step 3: Rewrite the orientation in `metrics/formation.py`**

Add the import near the top, under `import numpy as np`:

```python
from config.settings import settings
```

Replace `detect_formation`'s signature and body down to `oriented = ...`:

```python
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
```

Replace `_mean_depths` entirely and delete `_orient_to_own_goal`:

```python
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
    if track.pitch_history:
        frames = track.frame_history
        return [
            _distance(
                float(pos[0]),
                _end_at(
                    own_goal_end,
                    half_time_frame,
                    frames[i] if i < len(frames) else None,
                ),
            )
            for i, pos in enumerate(track.pitch_history)
        ]
    if track.pitch_pos is not None:
        return [_distance(float(track.pitch_pos[0]), own_goal_end)]
    return []


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
```

Also add `Track` to the `TYPE_CHECKING` import at the top:

```python
if TYPE_CHECKING:
    from tracking.types import Track, TrackedFrame
```

And add this paragraph to the module docstring, after the "Given the own-goal end, detection is:" list:

```
Teams change ends at half-time, so the own-goal end is a property of *when* an
observation was made, not of the match. Pass half_time_frame and each position
is measured from the goal that team was actually defending at the time; without
it the whole video is treated as one direction, and a full match reports a
blend of the true shape and its mirror.
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `/usr/local/bin/python3.11 -m pytest tests/test_metrics/test_formation.py -q`
Expected: PASS, 25 tests. **All 19 pre-existing tests must still pass without edits.**

Then the full suite and lint:

Run: `/usr/local/bin/python3.11 -m pytest tests/ -q --ignore=tests/test_detection && /usr/local/bin/python3.11 -m ruff check .`
Expected: 297 passed, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add metrics/formation.py tests/test_metrics/test_formation.py
git commit -m "fix(formation): orient each position to the goal its team was defending"
```

---

### Task 2: `Match.half_time_seconds` column and migration

**Files:**
- Modify: `database/models.py` (after `home_defends_end`, around line 113)
- Create: `alembic/versions/a4c7e912b6d3_add_half_time_to_match.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Match.half_time_seconds: Mapped[Optional[float]]`. Tasks 3 and 4 read and write it.

- [ ] **Step 1: Add the column**

In `database/models.py`, immediately after the `home_defends_end` mapped column and its comment block:

```python
    # Seconds into the video at which the teams change ends. NULL means the
    # video is one half, or that the coach did not say — either way the whole
    # video is treated as one direction, which is what happened before this
    # column existed. Never inferred: a wrong split mirrors half the match
    # while looking calibrated, which is the bug it exists to remove.
    # Stored in seconds rather than frames so a later correction to `fps`
    # cannot silently move it to a different moment in the video.
    half_time_seconds: Mapped[Optional[float]] = mapped_column(Float)
```

`Float` and `Optional` are already imported in this file.

- [ ] **Step 2: Write the migration**

Create `alembic/versions/a4c7e912b6d3_add_half_time_to_match.py`:

```python
"""add_half_time_to_match

Revision ID: a4c7e912b6d3
Revises: f7b2c9d4e310
Create Date: 2026-08-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4c7e912b6d3'
down_revision: Union[str, Sequence[str], None] = 'f7b2c9d4e310'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('matches', schema=None) as batch_op:
        # Nullable with no server default: NULL is the meaningful "not stated"
        # value, and every existing row genuinely has not stated it.
        batch_op.add_column(sa.Column('half_time_seconds', sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('matches', schema=None) as batch_op:
        batch_op.drop_column('half_time_seconds')
```

- [ ] **Step 3: Verify the head is unique and the migration runs both ways**

```bash
cp dev.db /tmp/dev.db.task2-bak
/usr/local/bin/python3.11 -m alembic heads
/usr/local/bin/python3.11 -m alembic upgrade head
/usr/local/bin/python3.11 -c "import sqlite3;print([r[1] for r in sqlite3.connect('dev.db').execute('PRAGMA table_info(matches)')])"
/usr/local/bin/python3.11 -m alembic downgrade -1
/usr/local/bin/python3.11 -m alembic upgrade head
```

Expected: `heads` prints `a4c7e912b6d3 (head)` and nothing else; the column list contains `half_time_seconds` after upgrade; downgrade and re-upgrade both succeed with no error.

- [ ] **Step 4: Run the suite**

Run: `/usr/local/bin/python3.11 -m pytest tests/ -q --ignore=tests/test_detection && /usr/local/bin/python3.11 -m ruff check .`
Expected: 297 passed, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add database/models.py alembic/versions/a4c7e912b6d3_add_half_time_to_match.py
git commit -m "feat(db): record when the teams change ends"
```

---

### Task 3: `half_time_seconds` on the calibration endpoint

**Files:**
- Modify: `api/routers/matches.py` — `MatchCalibration` (docstring + field), `set_calibration` (persist)
- Test: `tests/test_api/test_calibration.py`

**Interfaces:**
- Consumes: `Match.half_time_seconds` from Task 2.
- Produces: `MatchCalibration.half_time_seconds: float | None`, request and response. Task 5's picker sends it.

**Note:** `MatchCalibration` is the `response_model` as well as the request body, so this is a **visible wire-format change**. `test_stores_corners_and_defended_end` asserts the response dict exactly and must be updated — that is the point of the assertion, not a nuisance.

- [ ] **Step 1: Write the failing tests**

In `tests/test_api/test_calibration.py`, update the existing exact-dict assertion inside `TestSetCalibration.test_stores_corners_and_defended_end`:

```python
        assert resp.json() == {
            "pitch_corners": VALID_CORNERS,
            "home_defends_end": "low",
            "half_time_seconds": None,
        }
```

Then append a new class:

```python
class TestHalfTime:

    def test_stores_half_time_seconds(self, client, seeded, db_session):
        match_id = seeded["match"].id
        resp = _put(client, match_id, half_time_seconds=2730.5)

        assert resp.status_code == 200
        assert resp.json()["half_time_seconds"] == 2730.5

        db_session.expire_all()
        assert db_session.get(Match, match_id).half_time_seconds == 2730.5

    def test_omitting_it_stores_null(self, client, seeded, db_session):
        match_id = seeded["match"].id
        assert _put(client, match_id).status_code == 200

        db_session.expire_all()
        assert db_session.get(Match, match_id).half_time_seconds is None

    def test_clearing_it_is_possible(self, client, seeded, db_session):
        """A coach who mis-typed the mark must be able to take it back, not
        just overwrite it — omitting the field is how the picker clears it."""
        match_id = seeded["match"].id
        _put(client, match_id, half_time_seconds=2700.0)
        _put(client, match_id)

        db_session.expire_all()
        assert db_session.get(Match, match_id).half_time_seconds is None

    def test_rejects_zero(self, client, seeded):
        assert _put(client, seeded["match"].id,
                    half_time_seconds=0).status_code == 422

    def test_rejects_negative(self, client, seeded):
        assert _put(client, seeded["match"].id,
                    half_time_seconds=-1.0).status_code == 422

    def test_rejects_non_numeric(self, client, seeded):
        assert _put(client, seeded["match"].id,
                    half_time_seconds="45:30").status_code == 422
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/usr/local/bin/python3.11 -m pytest tests/test_api/test_calibration.py -q`
Expected: FAIL — the new tests get `None` back (extra fields are ignored, so nothing is stored), and the updated exact-dict assertion fails on the missing key.

- [ ] **Step 3: Add the field and persist it**

In `api/routers/matches.py`, add to `MatchCalibration`'s docstring, after the `home_defends_end` paragraph:

```
    half_time_seconds: seconds into the video at which the teams change ends,
                      or omitted when the video is one half. Positions after it
                      are measured from the opposite goal; without it a full
                      match reports a blend of the true shape and its mirror.
                      Seconds rather than frames so a later `fps` correction
                      cannot silently move it.
```

Add the field below `home_defends_end`:

```python
    home_defends_end: Literal["low", "high"]
    half_time_seconds: Optional[float] = Field(default=None, gt=0)
```

`Optional` and `Field` are already imported in this file.

In `set_calibration`, add the assignment alongside the other two:

```python
    match.pitch_corners = calibration.pitch_corners
    match.home_defends_end = calibration.home_defends_end
    match.half_time_seconds = calibration.half_time_seconds
```

Assigning unconditionally is deliberate: the endpoint replaces a match's whole calibration, so an omitted mark clears a previous one rather than leaving a stale value behind a fresh set of corners.

Add to the route docstring, after the existing "Set this before uploading" paragraph:

```
    `half_time_seconds` is optional and only matters for a video covering both
    halves; leaving it out keeps the whole video in one direction.
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `/usr/local/bin/python3.11 -m pytest tests/test_api/test_calibration.py -q`
Expected: PASS.

Run: `/usr/local/bin/python3.11 -m pytest tests/ -q --ignore=tests/test_detection && /usr/local/bin/python3.11 -m ruff check .`
Expected: 303 passed, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add api/routers/matches.py tests/test_api/test_calibration.py
git commit -m "feat(api): accept a half-time mark with the calibration"
```

---

### Task 4: Convert seconds to a frame in `run_pipeline`

**Files:**
- Modify: `scripts/run_pipeline.py` — `run()` signature and docstring, the stage 5b block, the argparse section, the `run(...)` call at the bottom
- Modify: `tasks/pipeline.py` — the commented-out `run(...)` call
- Test: `tests/test_pipeline/test_positions.py`

**Interfaces:**
- Consumes: `detect_formation(..., half_time_frame=...)` from Task 1; `Match.half_time_seconds` from Task 2.
- Produces: `half_time_frame(half_time_seconds: float | None, fps: float) -> int | None` in `scripts/run_pipeline.py`, and `run(..., half_time_seconds: float | None = None)`.

**Background:** `frame_id` is a plain zero-based decode counter — `detection/detector.py::process_video` sets `frame_id = 0` and increments once per `cap.read()`, with no stride — so `round(seconds * fps)` is exact. `run()` already resolves `_fps` from the argument or `cfg.default_fps`; use `_fps`, never `cfg.default_fps` directly.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pipeline/test_positions.py`:

```python
# ---------------------------------------------------------------------------
# Half-time seconds -> frame
# ---------------------------------------------------------------------------

class TestHalfTimeFrame:

    def test_none_stays_none(self):
        assert half_time_frame(None, 25.0) is None

    def test_converts_with_the_match_fps(self):
        assert half_time_frame(60.0, 25.0) == 1500
        assert half_time_frame(60.0, 30.0) == 1800

    def test_rounds_rather_than_truncates(self):
        """A frame is 40 ms at 25 fps; truncating biases every mark early."""
        assert half_time_frame(1.98, 25.0) == 50

    def test_non_positive_fps_is_declined(self):
        """A bad fps would put half-time at frame 0 — i.e. mirror the whole
        match — so it degrades to "no split" instead."""
        assert half_time_frame(60.0, 0.0) is None
        assert half_time_frame(60.0, -25.0) is None
```

and add it to the existing module-level import block at the top of the file,
which is where this file already imports `_OPPOSITE_END` from:

```python
from scripts.run_pipeline import (
    _OPPOSITE_END,
    PITCH_MARGIN_M,
    clamp_to_pitch,
    feet_pixels,
    half_time_frame,
)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/usr/local/bin/python3.11 -m pytest tests/test_pipeline/test_positions.py -q`
Expected: FAIL with `ImportError: cannot import name 'half_time_frame'`.

- [ ] **Step 3: Implement the conversion and thread the argument**

In `scripts/run_pipeline.py`, add next to `_OPPOSITE_END` (around line 28):

```python
def half_time_frame(half_time_seconds: float | None, fps: float) -> int | None:
    """The frame at which the teams change ends, or None if not stated.

    frame_id is a plain zero-based decode counter (detector.process_video
    increments it once per cap.read(), with no stride), so this is exact.

    A non-positive fps would land the split on frame 0 and mirror the entire
    match, so it declines instead — the same correct-or-silent stance the rest
    of the calibration path takes.
    """
    if half_time_seconds is None or fps <= 0:
        return None
    return round(half_time_seconds * fps)
```

Add the parameter to `run()` after `home_defends_end`:

```python
    home_defends_end: str | None = None,
    half_time_seconds: float | None = None,
```

Add to `run()`'s docstring, after the `home_defends_end` line:

```
    half_time_seconds: seconds into the video at which the teams change ends.
                      None (the default) treats the whole video as one
                      direction. Converted to a frame here, where fps is
                      resolved; detect_formation takes frames.
```

Replace the stage 5b block:

```python
    # --- Stage 5b: Formation detection ---
    # The away team defends the opposite end. When the match has no annotated
    # direction both stay "unknown" by design — a confidently wrong formation is
    # worse than none for a coach.
    #
    # The half-time mark orients each observation to the goal that team was
    # actually defending at the time; without it a video covering both halves
    # averages a shape with its own mirror.
    away_defends_end = _OPPOSITE_END.get(home_defends_end or "")
    split = half_time_frame(half_time_seconds, _fps)
    if half_time_seconds is not None and split is None:
        logger.warning(
            f"half_time_seconds given with an unusable fps ({_fps}) — "
            "treating the video as one direction"
        )
    elif split is not None and not home_defends_end:
        # Inert rather than wrong: detect_formation declines without a
        # direction, so the mark changes nothing. Said out loud because a coach
        # who filled it in has reason to expect it mattered.
        logger.warning(
            "half_time_seconds given without a usable home_defends_end — "
            "formations stay \"unknown\", so the half-time mark has no effect"
        )
    home_formation = detect_formation(
        all_tracked_frames, team="home",
        own_goal_end=home_defends_end, half_time_frame=split,
    )
    away_formation = detect_formation(
        all_tracked_frames, team="away",
        own_goal_end=away_defends_end, half_time_frame=split,
    )
    logger.info(f"Formation — home: {home_formation}, away: {away_formation}")
```

Add the CLI flag alongside `--home-defends-end` in the argparse section:

```python
    parser.add_argument("--half-time-seconds", type=float, default=None,
                        help="Seconds into the video at which the teams change "
                             "ends. Omit for a video covering one half.")
```

And pass it in the `run(...)` call at the bottom:

```python
        home_defends_end=args.home_defends_end,
        half_time_seconds=args.half_time_seconds,
```

In `tasks/pipeline.py`, extend the commented-out call so the argument is not lost when torch arrives:

```python
        #     pitch_corners=match.pitch_corners if match else None,
        #     home_defends_end=match.home_defends_end if match else None,
        #     half_time_seconds=match.half_time_seconds if match else None)
```

(and drop the now-misplaced `)` from the `home_defends_end` line).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `/usr/local/bin/python3.11 -m pytest tests/test_pipeline/test_positions.py -q`
Expected: PASS.

Run: `/usr/local/bin/python3.11 -m pytest tests/ -q --ignore=tests/test_detection && /usr/local/bin/python3.11 -m ruff check .`
Expected: 307 passed, ruff clean.

Check the flag is wired:

Run: `PYTHONPATH=. /usr/local/bin/python3.11 scripts/run_pipeline.py --help`
Expected: `--half-time-seconds` appears in the usage output.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_pipeline.py tasks/pipeline.py tests/test_pipeline/test_positions.py
git commit -m "feat(pipeline): pass the half-time mark through to formation detection"
```

---

### Task 5: The `mm:ss` input on the calibration screen

**Files:**
- Create: `dashboard/lib/half-time.ts`
- Create: `dashboard/lib/half-time.test.ts`
- Modify: `dashboard/components/CalibratePicker.tsx` — state, the input inside the "Attacking direction" card, `canSave`, `save()`

**Interfaces:**
- Consumes: `MatchCalibration.half_time_seconds` from Task 3. The proxy at `dashboard/app/api/matches/[id]/calibration/route.ts` forwards the body verbatim, so **it needs no change**.
- Produces: `parseHalfTime(value: string): { seconds: number | null; problem: string | null }`.

**Background:** the picker is a client component; the corner-scaling logic lives in `lib/corners.ts` as a pure module precisely because it fails silently when wrong. `mm:ss` parsing is the same kind of code, so it goes in its own module with tests. Note the hard-won bug from the last picker session: **`some`/`every`/`filter` skip array holes** — not relevant here, but the same instinct applies, prefer explicit checks over clever ones.

- [ ] **Step 1: Write the failing tests**

Create `dashboard/lib/half-time.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { parseHalfTime } from "./half-time";

describe("parseHalfTime", () => {
  it("reads mm:ss as seconds", () => {
    expect(parseHalfTime("45:30")).toEqual({ seconds: 2730, problem: null });
  });

  it("accepts hours for a long recording", () => {
    expect(parseHalfTime("1:05:00")).toEqual({ seconds: 3900, problem: null });
  });

  it("treats empty input as not stated", () => {
    expect(parseHalfTime("")).toEqual({ seconds: null, problem: null });
    expect(parseHalfTime("   ")).toEqual({ seconds: null, problem: null });
  });

  it("rejects a bare number, which is ambiguous", () => {
    // "45" could be 45 seconds or 45 minutes, and getting it wrong mirrors
    // half the match — so it is refused rather than guessed.
    expect(parseHalfTime("45").problem).not.toBeNull();
  });

  it("rejects seconds outside a minute", () => {
    expect(parseHalfTime("45:75").problem).not.toBeNull();
  });

  it("rejects nonsense", () => {
    expect(parseHalfTime("halftime").problem).not.toBeNull();
    expect(parseHalfTime("45:").problem).not.toBeNull();
    expect(parseHalfTime("-1:00").problem).not.toBeNull();
  });

  it("rejects zero, which the API rejects too", () => {
    expect(parseHalfTime("0:00").problem).not.toBeNull();
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd dashboard && npx vitest run lib/half-time.test.ts`
Expected: FAIL — cannot resolve `./half-time`.

- [ ] **Step 3: Write the parser and wire it into the picker**

Create `dashboard/lib/half-time.ts`:

```ts
/**
 * Parse the coach's half-time mark.
 *
 * The value is time into the *video*, not the match clock — that is what the
 * coach is scrubbing. A bare number is refused rather than guessed at: "45"
 * reads as either 45 seconds or 45 minutes, and a wrong split mirrors half the
 * match while looking calibrated, which is the bug this input exists to remove.
 *
 * `api/routers/matches.py` takes seconds and rejects anything <= 0; this
 * rejects the same values so the coach hears about it before the round trip.
 */
const HMS = /^(?:(\d+):)?([0-5]?\d):([0-5]\d)$/;

export function parseHalfTime(value: string): {
  seconds: number | null;
  problem: string | null;
} {
  const trimmed = value.trim();
  if (!trimmed) return { seconds: null, problem: null };

  const match = HMS.exec(trimmed);
  if (!match) {
    return {
      seconds: null,
      problem: "Enter the half-time mark as mm:ss (for example 45:30).",
    };
  }

  const [, hours, minutes, seconds] = match;
  const total =
    Number(hours ?? 0) * 3600 + Number(minutes) * 60 + Number(seconds);

  if (total <= 0) {
    return {
      seconds: null,
      problem: "Half-time cannot be at the very start of the video.",
    };
  }
  return { seconds: total, problem: null };
}
```

In `dashboard/components/CalibratePicker.tsx`:

Add state next to `defendsEnd`:

```tsx
  const [halfTime, setHalfTime] = useState("");
```

Import the parser alongside the corners import:

```tsx
import { parseHalfTime } from "@/lib/half-time";
```

Derive the parse result next to `problem` / `canSave` and block saving on a bad value:

```tsx
  const problem = corners.length === 4 ? quadProblem(corners) : null;
  const halfTimeParsed = parseHalfTime(halfTime);
  const canSave =
    corners.length === 4 &&
    !problem &&
    defendsEnd !== null &&
    halfTimeParsed.problem === null;
```

Send it in `save()`:

```tsx
        body: JSON.stringify({
          pitch_corners: corners.map((p) => [p.x, p.y]),
          home_defends_end: defendsEnd,
          half_time_seconds: halfTimeParsed.seconds,
        }),
```

Add the input inside the existing "Attacking direction" card, after the closing `</div>` of the radio list and before the "Left and right as they appear" paragraph:

```tsx
          <div className="mt-4 border-t border-slate-100 pt-4">
            <label
              htmlFor="half-time"
              className="text-sm font-medium text-slate-700"
            >
              Half-time (optional)
            </label>
            <p id="half-time-help" className="mt-1 text-xs text-slate-400">
              If this video covers both halves, the time on the video when the
              teams changed ends — mm:ss. Leave it blank for a single half.
            </p>
            <input
              id="half-time"
              type="text"
              inputMode="numeric"
              placeholder="45:30"
              value={halfTime}
              onChange={(e) => {
                setHalfTime(e.target.value);
                setSaved(false);
              }}
              aria-describedby="half-time-help"
              aria-invalid={halfTimeParsed.problem !== null}
              className="mt-2 w-32 rounded border border-slate-200 px-2 py-1 font-mono text-sm text-slate-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
            />
            {halfTimeParsed.problem && (
              <p role="alert" className="mt-2 text-xs text-amber-700">
                {halfTimeParsed.problem}
              </p>
            )}
          </div>
```

- [ ] **Step 4: Run the tests and the type check**

Run: `cd dashboard && npx vitest run && ./node_modules/.bin/tsc --noEmit`
Expected: 48 vitest pass, tsc clean.

- [ ] **Step 5: Drive it in a real browser**

The last two sessions each found bugs that `tsc` and unit tests both passed. Do not skip this.

```bash
# terminal 1
cd /Users/amrabujabal/Downloads/pitchvision
PYTHONPATH=. REDIS_URL="memory://" /usr/local/bin/python3.11 -m uvicorn api.main:app --port 8001
# terminal 2
cd /Users/amrabujabal/Downloads/pitchvision/dashboard && TZ=UTC npm run dev
```

Sign in as `7ceca9ce-9c63-4330-8053-d658408c9fc6` / `devpassword`, open a match's calibrate screen, place four corners, choose a direction, then check:

1. Typing `45:30` and saving stores `2730.0`. Read it back — remember **`dev.db` stores match ids without dashes**, so a `WHERE id='<dashed-uuid>'` updates and selects nothing while reporting success:
   ```bash
   /usr/local/bin/python3.11 -c "import sqlite3;print(list(sqlite3.connect('dev.db').execute('select id, half_time_seconds from matches')))"
   ```
2. Typing `45` shows the mm:ss message and the Save button is disabled.
3. Clearing the field back to empty re-enables Save and stores NULL.
4. If the page 404s on its own CSS and chunks, that is the stale `.next` cache — kill the dev server, `rm -rf .next`, restart. It is not a code fault.

- [ ] **Step 6: Commit**

```bash
git add dashboard/lib/half-time.ts dashboard/lib/half-time.test.ts dashboard/components/CalibratePicker.tsx
git commit -m "feat(dashboard): let the coach mark half-time on the calibration screen"
```

---

## Final verification

- [ ] `/usr/local/bin/python3.11 -m pytest tests/ -q --ignore=tests/test_detection` → **307 pass**
- [ ] `/usr/local/bin/python3.11 -m pytest tests/test_api/ tests/test_db/ -q` → 183 pass
- [ ] `/usr/local/bin/python3.11 -m ruff check .` → clean
- [ ] `cd dashboard && ./node_modules/.bin/tsc --noEmit && npx vitest run` → clean, 48 pass
- [ ] `/usr/local/bin/python3.11 -m alembic heads` → one head, `a4c7e912b6d3`
- [ ] `/simplify`, then `/code-review high`, then `/security-review` (this touches input parsing and a DB write reachable from the browser), then `/karpathy-check` before the final commit
- [ ] Update `CLAUDE.md`'s test counts and add the half-time invariant
- [ ] Update `handoff.md`: goal, current state, active files, changes made, failed attempts, next steps

Expected test-count arithmetic: 291 baseline + 6 (Task 1) + 6 (Task 3) + 4 (Task 4) = 307 pytest; 41 + 7 (Task 5) = 48 vitest. If a count comes out lower, a test is being skipped or collected under the wrong name — find out which before moving on.
