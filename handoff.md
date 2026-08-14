# PitchVision — Handoff

_Last updated: 2026-08-13_ — **formation detection is live end to end.**

## Goal

Take formation detection from a correct-but-dead function to a number a coach
actually sees: pitch calibration on the match record → real homography →
per-frame pitch positions → formation → DB → API → dashboard.

## Current State

- **235 tests pass** locally (`pytest tests/ -q --ignore=tests/test_detection`),
  **135 in CI scope** (`tests/test_api/ tests/test_db/`, was 126). `ruff check .`
  clean; dashboard `tsc --noEmit` clean.
- Formation now flows: `PUT /matches/{id}/calibration` → `Match.pitch_corners` +
  `home_defends_end` → `PitchHomography.fit_from_corners()` → `track.pitch_history`
  → `detect_formation()` → `Match.home_formation` / `away_formation` → match
  summary API → a "Formation" KPI card on the match detail page.
- Migration `f7b2c9d4e310` adds the four new Match columns; verified up **and**
  down against a scratch SQLite DB.
- Three latent bugs found and fixed on the way in — see Changes Made.
- **Local env changed:** `alembic` and `opencv-python-headless` are now installed
  for python3.11. They were needed to verify the migration and to run any
  homography test at all. Neither is in `requirements-ci.txt`, so
  `tests/test_metrics/`, `tests/test_utils/` and `tests/test_pipeline/` still do
  not run in CI.

## Active Files

- `metrics/formation.py` — `_mean_depths` now reads the x axis and prefers
  `pitch_history`.
- `scripts/run_pipeline.py` — homography setup + `to_pitch()`, `feet_pixels()`,
  `_OPPOSITE_END`; heavy detection imports moved inside `run()` so the pure
  helpers import without torch.
- `utils/homography.py` — new `fit_from_corners()`.
- `database/models.py` + `alembic/versions/f7b2c9d4e310_*.py` — four new Match columns.
- `database/repository.py` — `PipelineResult` carries the formations; `save_pipeline_results` writes them.
- `api/routers/matches.py` — `MatchCalibration` + `PUT /{id}/calibration`.
- `dashboard/app/matches/[id]/page.tsx` + `lib/types.ts` — Formation KPI card.
- Tests: `tests/test_api/test_calibration.py` (new), `tests/test_pipeline/test_positions.py` (new),
  `tests/test_metrics/test_formation.py`, `tests/test_utils/test_homography.py`.

## Changes Made

Three real bugs surfaced while reading the code, all fixed:

1. **Axis convention was inverted in `formation.py`.** Every other module treats
   x as pitch length (goal-to-goal) — `homography._standard_corners`,
   `pitch_control` grids, `pressing`'s goal at `[pitch_length, pitch_width/2]` —
   but `_mean_depths` read `pitch_pos[1]` as depth, and its 18 tests baked in the
   same inversion, as did `CLAUDE.md`. Invisible while `pitch_pos` was unset;
   it would have produced a confidently wrong formation the moment homography
   landed. Fixed in the function, its fixtures, and the convention line.
2. **`track.pitch_history` was never populated anywhere in the codebase.** That
   also silently zeroed `pitch_control.compute_player_pitch_control_summary`
   (returns 0.0 for every track) and `pressing.recovery_angle` (always 0.0). The
   pipeline now fills it for every confirmed track, fixing all three consumers.
3. **Frame-loop aggregation was a no-op.** The tracker puts the _same_ `Track`
   objects into every `TrackedFrame`, so summing `pitch_pos` per frame averaged
   the final frame N times. `_mean_depths` now reads each track once and uses
   its real per-frame history.

Also: positions are taken from the **bottom edge** of each box (where a player
meets the ground) rather than its centre — the centre projects a torso onto the
pitch plane and pushes positions away from the camera under a real homography.

Code review then caught a fourth real one: **stages 3 and 4 (pitch control,
pressing) run before stage 5 publishes positions**, so with calibration set they
were still using their own linear pixel map while physical metrics and formation
used real metres — two coordinate systems in one report. Both now take
`homography=` directly. Also added: a clamp on projected positions (a point past
the horizon projects to ~-28 m and would otherwise become metres of travel),
a `try/except` so a ragged `pitch_corners` JSON row degrades instead of failing
the match, and `home_defends_end` is now ignored without a working homography
(labelling a shape off the crude linear stretch is the confidently-wrong answer
`formation.py` exists to refuse).

Fixed a pre-existing CI failure: an unused `pytest` import in
`test_formation.py` had `ruff check .` failing since `a5f88be`, so the backend
lint job was red — the previous handoff's "CI green" predated it.

## Failed Attempts

- Nothing failed outright this session. One thing worth not re-litigating:
  **`own_goal_end` cannot be derived from the pitch corners.** A homography
  gives you where the goals _are_, not which team defends which one. It has to
  be supplied per match, which is why the calibration payload carries it.

## Next steps

1. **Corner-picker UI** — the calibration endpoint has no dashboard screen. A
   coach today needs a raw `PUT`. Click four corners on a still from the video.
2. **Re-processing after calibration** — uploading starts the pipeline
   immediately, so calibration saved afterwards only takes effect next run.
   Either have `PUT /calibration` re-enqueue, or split upload from "start".
3. **Half-time end swap** — `home_defends_end` describes the whole video, so a
   full-match upload mirrors one half's formation. Needs a per-half split.
4. Consider adding opencv to `requirements-ci.txt` so `tests/test_metrics/`,
   `tests/test_utils/` and `tests/test_pipeline/` actually run in CI — the
   homography and formation tests are currently local-only.
5. Backlog unchanged: Re-ID across occlusions (needs torch), pgvector player search.

## How to resume / verify

- `cd /Users/amrabujabal/Downloads/football-ai`
- CI scope: `/usr/local/bin/python3.11 -m pytest tests/test_api/ tests/test_db/ -q` → 135 pass
- Wider: `/usr/local/bin/python3.11 -m pytest tests/ -q --ignore=tests/test_detection` → 235 pass
- Lint: `/usr/local/bin/python3.11 -m ruff check .` → clean
- Dashboard: `cd dashboard && ./node_modules/.bin/tsc --noEmit` → clean
- `tests/test_detection/` still needs torch/ultralytics — not installed here.
- API live: `https://pitchvision-api-4hxfthgkna-uc.a.run.app/health`
