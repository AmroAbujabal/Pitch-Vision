# PitchVision — Handoff

_Last updated: 2026-08-19_ — **the half-time end swap is built and green on the
branch `half-time-end-swap`, not merged and not pushed.** Five tasks, all through
task review; one fix round on the dashboard parser after a browser check.

**One fix wave remains before merge.** The final whole-branch review approved the
branch with two Important findings and four Minor ones, and it was NOT dispatched —
the session hit a usage checkpoint first. The complete findings list, in the order to
hand to a single fix subagent, is in
`.superpowers/sdd/2026-08-19-half-time-end-swap/progress.md` under
"Final whole-branch review". Pick it up at next-steps item 1.

## Goal

Next-steps item 1 from the previous handoff: `home_defends_end` described the whole
video, so a full match had one half's positions mirrored along the pitch length axis
before averaging — the same silent-wrong-answer family as the corner-winding bug
`cf5a67d` closed, but reachable even when the calibration is perfect.

Designed and approved this session, then specced, planned, and executed through
subagent-driven development.

## Current State

- **Branch `half-time-end-swap`, 7 commits off `main` at `fd190cc`. Working tree
  clean. Nothing pushed, nothing merged.**
  - `77ab2d0` docs: design and plan
  - `e8b7481` fix(formation): orient each position to the goal its team was defending
  - `9d65001` feat(db): record when the teams change ends
  - `efa9379` feat(api): accept a half-time mark with the calibration
  - `8e3aa35` feat(pipeline): pass the half-time mark through to formation detection
  - `d77b2b9` feat(dashboard): let the coach mark half-time on the calibration screen
  - `dbe3a1d` fix(dashboard): accept half-time marks past minute 59 in mm:ss
- **Verified at checkpoint, all green:** 307 pytest (was 291) / 183 API subset (was
  177) / ruff clean / `alembic heads` single at `a4c7e912b6d3` / 53 vitest (was 41) /
  `tsc --noEmit` clean.
- **Driven in a real browser**, API on 8001 with `REDIS_URL="memory://"`, dashboard
  under `TZ=UTC`, against match `72919811-…`:
  - `45:30` → `dev.db half_time_seconds = 2730.0`; clearing the field → NULL.
  - `45` and `5:5` → Save disabled, `aria-invalid=true`, alert announced.
  - `72:15` → rejected before the fix, `4335.0` after it.
- **Reviews:** a task review per task (all spec ✅, all quality approved), one scoped
  re-review of the fix round, and a final whole-branch review on the most capable
  model. The final review independently re-derived the two load-bearing claims —
  the constant-offset algebra and the history index alignment — from the tracker and
  pipeline source rather than the docstrings, and both hold.
- **`dev.db` was restored**: match `72919811-…` had its `pitch_corners`,
  `home_defends_end` and `half_time_seconds` set back to NULL after the browser
  drive, because the corners were for a 1280x720 test clip while the match record
  says 1920x1080. Nothing else was left behind. Pre-session copy at
  `/private/tmp/claude-501/-Users-amrabujabal/edd70e0d-5c07-4af0-b9a5-a4810a581cab/scratchpad/dev.db.session-bak`.

## Active Files

New:

- `docs/superpowers/specs/2026-08-19-half-time-end-swap-design.md` — the design.
- `docs/superpowers/plans/2026-08-19-half-time-end-swap.md` — the 5-task plan.
- `alembic/versions/a4c7e912b6d3_add_half_time_to_match.py`
- `dashboard/lib/half-time.ts` + `half-time.test.ts` — `parseHalfTime`, the mm:ss
  parsing, kept pure for the same reason `lib/corners.ts` is.

Modified:

- `metrics/formation.py` — the whole behaviour change. `_orient_to_own_goal` deleted.
- `database/models.py`, `api/routers/matches.py`, `scripts/run_pipeline.py`,
  `tasks/pipeline.py` (the commented-out `run(...)` call only).
- `tests/test_metrics/test_formation.py` (+6), `tests/test_api/test_calibration.py`
  (+6), `tests/test_pipeline/test_positions.py` (+4), `dashboard/lib/half-time.test.ts` (7),
  `dashboard/components/CalibratePicker.tsx`.

## Changes Made

1. **Orientation is now absolute and per-observation.** `_orient_to_own_goal` flipped
   a "high" team with `s.max() - s`, anchored on the deepest *observed* player. Fine
   for one direction — every downstream read is a difference — but two halves flipped
   about two different anchors are not on a common scale. Now each observation
   converts to `x` or `settings.pitch_length - x` before the per-track mean.
2. **Behaviour-preserving for the no-swap path, and that was the test.** `L - s` and
   `max(s) - s` differ by the constant `L - max(s)`, so all **19 pre-existing
   formation tests pass unedited**. They were treated as the check on the reasoning,
   not as tests to update.
3. **The half is a filter, not new plumbing.** `bbox_history` and `frame_history` are
   appended together in `tracker._new_track`/`_update_track`, and `run_pipeline`
   builds `pitch_history` 1:1 from `bbox_history`, so `frame_history[i]` dates
   `pitch_history[i]`. No tracker changes.
4. **Seconds stored, frame derived.** `frame_id` is a plain zero-based decode counter
   with no stride, so `round(seconds * fps)` is exact. Stored as seconds because a
   later correction to `fps` would silently move a stored *frame* to a different
   moment. `detect_formation` never learns about `fps`.
5. **One formation per team, unchanged.** Both halves become distances from their own
   goal, so `home_formation`/`away_formation` keep their meaning and use more data
   than either half alone. No new columns beyond `half_time_seconds`, no dashboard
   rendering change.
6. **The coach enters `mm:ss`** next to the direction radios; blank means one
   direction. Never inferred — a wrong split is exactly the mirror being removed.

## Failed Attempts

1. **A test in the plan was wrong, caught before dispatch.** The plan first asserted
   that a declared split changes nothing on static positions. It would have failed: a
   declared split *is* trusted, so unswapped positions get their second half mirrored
   and every player averages with their own mirror — all 11 land on x=52.5, reported
   as `"11"`. Rewritten as `test_a_wrong_split_gives_a_wrong_answer`, which pins the
   risk the feature accepts, so a future auto-detection attempt has to argue with a
   test rather than pass quietly.
2. **The `mm:ss` parser rejected the normal case, and unit tests + `tsc` both passed.**
   Minutes were capped at `[0-5]?\d`, so `72:15` was refused with "Enter the half-time
   mark as mm:ss (for example 45:30)" — the format the coach just used, with no hint
   that `1:12:15` was required. Half-time in a full-match video is normally *past*
   minute 59, because any pre-match footage pushes it there. **Only driving the real
   page found it**; the task review had called it Minor. That is now the third session
   running where a browser found what type-checking and unit tests could not.
3. **The plan put a caption in the wrong place.** "Left and right as they appear in
   the still above." explained the two radio labels; the plan had the half-time block
   inserted between them, so it now reads as a caption for the half-time input. Not
   yet fixed — it is minor 3 in the fix wave.

## Next steps

1. **Run the one remaining fix wave, then merge.** The complete findings list is in
   `.superpowers/sdd/2026-08-19-half-time-end-swap/progress.md`. Headlines:
   - **`half_time_seconds` is unbounded at every layer and overflows.**
     `Field(default=None, gt=0)` accepts `1e308`, and `round(1e308 * 25.0)` raises
     `OverflowError` — confirmed directly. Blast radius today is zero because
     `tasks/pipeline.py`'s `run(...)` is still commented out; the day it is
     uncommented, an authenticated coach can crash a pipeline run with a request body.
     Fix is `le=86_400` on the API field and the same ceiling in `parseHalfTime`.
   - **`CLAUDE.md` was never updated.** Line 181 still lists this feature under
     Remaining backlog, and the test counts at :51, :68, :145, :161 still say 291.
     Merged as-is, the next session is told to build what already shipped.
   - Plus: the orphaned caption, `inputMode="numeric"` hiding the colon on the iOS
     keypad, the design doc under-counting dormant direction-dependent metrics, and
     the error `<p>` missing from `aria-describedby`.
   Then `/karpathy-check`, merge to `main`, push. **Do not open a PR.**
2. **Frame dimensions are never sent.** `CalibratePicker` knows the real
   `frame.width/height` but `POST /matches/` takes the 1920x1080 default and `PUT
   /calibration` has no field to correct it. This bit during the browser drive — the
   corners saved were for a 1280x720 clip against a record claiming 1920x1080, which
   is why the row had to be cleared afterwards.
3. **Zoned serialisation on the API side.** Naive `DateTime` columns serialise with no
   zone. ~15 lines of pydantic serialisers, no migration, would make `isoInstant`
   dead. Visible wire-format change, which is why it is not a drive-by.
4. **`DISPLAY_ZONE` is one global guess** (`dashboard/lib/dates.ts`). A `timezone`
   column on `Academy` is the upgrade; an env var is the cheap stopgap.
5. **Orphaned video files.** `upload_video` never deletes a previously uploaded file
   for the same match, so uploading a `.mov` then an `.mp4` leaks the `.mov`.
6. **`tasks/pipeline.py::process_match` has no test coverage at all.**
7. **A third copy of the fetch/busy/error pattern** across `CalibratePicker.save()`,
   `.upload()` and `ReprocessButton`. A `useApiAction` hook would fold all three.
8. **The UUID regex is duplicated** — `dashboard/app/login/page.tsx:8` is
   character-for-character `lib/proxy.ts`'s exported `isUuid`.
9. **`Intl.DateTimeFormat` is rebuilt per call** in `dates.ts` (~164µs vs 1.6µs
   reusing one). Measurement already done; re-add the cache only if a page is slow.
10. **Cloud Run returned 503** on `/health` (2026-08-16). Still untouched.
11. Backlog: half-time per-half formation output if a coach ever asks; email/slug on
    `Academy` so login is not a raw UUID; the empty `api/routers/academies.py`; Re-ID
    across occlusions (needs torch); pgvector.

## How to resume / verify

- `git checkout half-time-end-swap`
- What CI runs: `/usr/local/bin/python3.11 -m pytest tests/ -q --ignore=tests/test_detection` → 307
- Lint: `/usr/local/bin/python3.11 -m ruff check .` → clean
- Dashboard: `cd dashboard && ./node_modules/.bin/tsc --noEmit && npm test` → 53
- The SDD ledger, briefs, reports and review packages are in
  `.superpowers/sdd/2026-08-19-half-time-end-swap/` (git-ignored). **Do not delete it
  until the fix wave is merged** — it is the only record of the findings.
- To drive the picker: API `PYTHONPATH=. REDIS_URL="memory://" python3.11 -m uvicorn
  api.main:app --port 8001`, dashboard `cd dashboard && TZ=UTC npm run dev`.
  Test academy `7ceca9ce-9c63-4330-8053-d658408c9fc6` / `devpassword`.
- **The picker needs a decodable video** to extract a frame. `data/raw/`'s only file
  is a 5-byte stub. Make one: `ffmpeg -f lavfi -i testsrc=size=1280x720:rate=25 -t 3
  -pix_fmt yuv420p out.mp4`. Playwright MCP can only read files under
  `/Users/amrabujabal` — put it there, not in the scratchpad.
- Clicking canvas corners through Playwright is unreliable; the picker's
  "Enter coordinates instead" panel has `#corner-N-x` / `#corner-N-y` inputs. Use those.
- `dev.db` stores match ids **without dashes**; a `WHERE id='<dashed>'` updates zero
  rows and reports success.
