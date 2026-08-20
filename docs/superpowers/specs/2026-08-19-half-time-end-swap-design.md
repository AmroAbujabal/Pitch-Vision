# Half-time end swap

_Design doc. Written 2026-08-19._

## Problem

`Match.home_defends_end` describes the whole video. Teams change ends at
half-time, so on any full match one half's positions are mirrored along the
pitch length axis before they are averaged, and the reported formation is a
blend of the true shape and its reverse.

This is the same failure family as the corner-winding bug fixed in `cf5a67d`:
a confident wrong answer with nothing downstream able to notice. `cf5a67d`
closed the "coach clicked the corners in the wrong order" door. This one is
open even when the calibration is perfect.

It is the largest remaining correctness gap in the analytics.

## Scope

In: a coach-supplied half-time mark, a formation detector that orients each
observation to the end its team was actually defending at that moment, and the
one field threaded through migration, API, picker and `run_pipeline`.

Out: per-half formation output; automatic half-time detection; extra-time and
multi-break formats; wiring up `compute_dangerous_zone_occupancy`; sending real
frame dimensions from the picker (a separate filed item); anything in the
dashboard beyond the one new input.

## Approach

### The split is coach-supplied, and stored in seconds

The calibration screen already asks the coach for something only they know —
which end the home team defends, because a homography tells you where the goals
are but not who defends which one. The half-time mark is the same kind of fact
and goes next to it: an `mm:ss` input, on the screen where the coach is already
scrubbing the video.

`half_time_seconds` NULL means today's whole-video behaviour. Absent input is
never guessed at, for the reason `home_defends_end` is not guessed at either: a
wrong split re-introduces exactly the mirror this work exists to remove, and
does it while looking calibrated.

**Seconds, not a frame number.** `frame_id` is a plain zero-based decode
counter — `detection/detector.py::process_video` increments it once per
`cap.read()` with no stride — so `round(seconds * fps)` converts exactly at read
time. The deciding argument is the failure mode of being wrong later: if
`Match.fps` is ever corrected, a stored frame number silently comes to mean a
different moment in the video, while a stored second stays right. The conversion
is done where `fps` is known, so nothing else has to carry both numbers.

The value is time into the *video*, not the match clock. That is what the coach
is scrubbing, and a video that starts before kickoff needs no separate offset.

### Orientation becomes absolute, and moves per-observation

`_orient_to_own_goal` currently flips a `"high"` team's depths with
`s.max() - s` — anchored on the deepest *observed* player. That is sound for a
single direction, because every downstream read (line clustering, the goalkeeper
isolation gap) is a difference. It cannot mix halves: two halves flipped about
two different anchors are not on a common scale.

Replace it with the absolute conversion, applied per observation inside
`_mean_depths` before the per-track mean:

    depth = x  if own_goal_end == "low"  else  settings.pitch_length - x

**This is behaviour-preserving for the no-swap path.** `L - s` and
`max(s) - s` differ by the constant `L - max(s)`, and nothing downstream reads
an absolute depth. The 19 existing `detect_formation` tests all pin the no-swap
path and are expected to pass unchanged; a failure there is a real finding
about this reasoning, not a test to update.

### The histories are index-aligned, so the half is a filter

`tracking/tracker.py` appends `bbox_history` and `frame_history` together in
both `_new_track` and `_update_track`, and `scripts/run_pipeline.py` builds
`pitch_history` one-for-one from `bbox_history` (`to_pitch` is (N,2) → (N,2),
and non-finite rows are pinned to the previous good position rather than
dropped, so the length is preserved).

So `pitch_history[i]` was observed at `frame_history[i]`, and attributing an
observation to a half is `frame_history[i] >= split_frame`. **No tracker
changes, no new plumbing on `Track`.**

`_mean_depths` has one fallback for tracks with no `pitch_history`, reading the
single latest `pitch_pos`. That has no frame to test, and `run_pipeline` cannot
produce it (it skips tracks with `len(bbox_history) < 2`, which is the only way
`pitch_history` ends up empty). Those observations are attributed to the first
half and the docstring says so, rather than growing a branch for a state the
pipeline cannot reach.

### Output stays one formation per team

Each observation is converted to "distance from the goal *that team* was
defending at that moment" and then averaged across the whole match. Both halves
land on a common scale, so `Match.home_formation` / `away_formation` keep their
current meaning and are computed from more data than either half alone.

No new columns beyond `half_time_seconds`, no change to the match summary API,
and no change to the Formation KPI card.

## Data model and wire format

- `Match.half_time_seconds: Mapped[Optional[float]]`, nullable, no server
  default. New alembic revision on top of the current head.
- `MatchCalibration` gains `half_time_seconds: float | None = None`, validated
  `> 0`. It is optional, so existing callers — `run_pipeline --pitch-corners`,
  any curl client — keep working unchanged.
- `run_pipeline` gains `half_time_seconds` (kwarg and `--half-time-seconds`),
  defaulting to None, alongside the existing `home_defends_end`.
- `detect_formation` gains `half_time_frame: int | None`. The detector is given
  a frame, not seconds: it has no `fps` and no reason to learn one. The
  seconds → frame conversion happens once, in `run_pipeline`, where `fps` is
  already resolved.

A half-time mark supplied without a usable `home_defends_end` is inert, the
same way `home_defends_end` without a homography is already downgraded to None
with a warning in `run_pipeline`. It should warn by the same route rather than
failing the run.

## Testing

- **Straddling tracks.** A synthetic track whose positions sit at one end
  before the split and the mirrored end after it must yield the same formation
  as a track that stays put — this is the test the 19 existing ones cannot
  express, because they all pin a single direction.
- **The mirror, demonstrated.** The same synthetic full match must produce the
  correct shape with the split set and the mirrored shape without it, so the
  test states the bug rather than only the fix.
- **Boundary.** An observation exactly at `split_frame` belongs to the second
  half; asserted directly, since off-by-one here is a silent half-swap.
- **Behaviour preservation.** The existing suite passes untouched, and the new
  absolute orientation is asserted to agree with the old relative one on the
  no-swap path.
- **`half_time_seconds` round-trips** through `PUT /calibration` under
  `get_scoped_match`, including the NULL case and a rejected `<= 0`.
- Migration up and down against `dev.db`.
- The picker driven in a real browser with the dev server under `TZ=UTC`,
  confirming the value reaches the DB.

## Rejected alternatives

- **Auto-detecting the swap** (e.g. a change in the mean depth of each team
  around the midpoint). A wrong guess produces precisely the silent mirror this
  work removes, and it would produce it on the matches where the data is
  weakest — partial-pitch views and sparse tracks. Declining is the stance
  `detect_formation` already takes for unknown direction.
- **Per-half formations as the output.** More columns, a dashboard change, and
  each half is labelled from half the data. Worth doing if a coach asks for it;
  it is not what the bug requires.
- **A second `home_defends_end` for the second half.** Redundant — the second
  half is by definition the opposite end — and it makes an inconsistent pair
  representable.
- **Splitting inside the tracker.** Needs tracker changes for something that is
  a read-time filter over data already recorded.

## Risks and known gaps

- **A wrong `mm:ss` is a new way to get a mirror**, in exchange for removing a
  guaranteed one. The input is on the screen where the coach is watching the
  video, which is the best available mitigation; there is no way to validate it
  server-side.
- **Two halves only.** Extra time and any format with more than one break stay
  wrong. Out of scope, and NULL leaves them exactly as they are today.
- **`compute_dangerous_zone_occupancy` remains direction-dependent and
  uncalled.** If it is ever wired up it needs the same per-observation
  treatment; formation is the only live direction-dependent metric today.
  Pressing's "direction" is toward the ball carrier, and physical metrics,
  pitch control and heatmaps are direction-agnostic.
