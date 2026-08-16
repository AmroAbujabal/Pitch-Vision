# PitchVision — Handoff

_Last updated: 2026-08-15_ — **formation detection live end to end; match API is
tenant-scoped. Working tree clean, both commits pushed to `origin/main`.**

## Goal

Two things shipped this session:

1. Take formation detection from a correct-but-dead function to a number a coach
   actually sees: pitch calibration on the match record → real homography →
   per-frame pitch positions → formation → DB → API → dashboard.
2. Close the cross-tenant access hole on the match API, found while reviewing (1).

## Current State

- **Verified 2026-08-15, after the last commit:**
  - CI scope `pytest tests/test_api/ tests/test_db/ -q` → **145 pass** (was 126)
  - Wider `pytest tests/ -q --ignore=tests/test_detection` → **245 pass**
  - `ruff check .` → clean; `cd dashboard && ./node_modules/.bin/tsc --noEmit` → clean
- Two commits pushed, tree clean, local == `origin/main`:
  - `d893af1` feat(formation): wire pitch calibration through to live formations
  - `5980461` fix(api): scope every match route to the calling academy
- Formation flows: `PUT /matches/{id}/calibration` → `Match.pitch_corners` +
  `home_defends_end` → `PitchHomography.fit_from_corners()` → `track.pitch_history`
  → `detect_formation()` → `Match.home_formation` / `away_formation` → summary API
  → "Formation" KPI card. Migration `f7b2c9d4e310`, verified up **and** down.
- Every per-match route depends on `get_scoped_match`; `db.get(Match, ...)` now
  appears exactly once in `api/routers/matches.py`.
- **Nobody can actually use formation detection yet** — the calibration endpoint
  has no dashboard screen, so it needs a hand-written `PUT`. The feature is live
  but unreachable.
- **Local env changed:** `alembic` and `opencv-python-headless` installed for
  python3.11 (needed to verify the migration and run any homography test).
  Neither is in `requirements-ci.txt`, so `tests/test_metrics/`,
  `tests/test_utils/` and `tests/test_pipeline/` — 100 of the 245 tests — still
  do not run in CI.

## Active Files

- `api/routers/matches.py` — `get_scoped_match` dependency; `MatchCalibration`; `PUT /{id}/calibration`.
- `metrics/formation.py` — `_mean_depths` reads the x axis and prefers `pitch_history`.
- `scripts/run_pipeline.py` — homography setup, `to_pitch()`, `clamp_to_pitch()`, `feet_pixels()`, `_OPPOSITE_END`; detection imports moved inside `run()` so the pure helpers import without torch.
- `utils/homography.py` — new `fit_from_corners()`.
- `database/models.py` + `alembic/versions/f7b2c9d4e310_*.py` — four new Match columns.
- `database/repository.py` — `PipelineResult` carries formations; `save_pipeline_results` writes them.
- `dashboard/app/matches/[id]/page.tsx`, `dashboard/lib/types.ts`, `lib/api.ts`.
- Tests: `test_api/test_calibration.py`, `test_api/test_tenant_isolation.py`,
  `test_pipeline/test_positions.py` (all new); `test_metrics/test_formation.py`,
  `test_utils/test_homography.py`, `test_api/conftest.py`.

## Changes Made

Five real bugs, four found by reading and one by `/code-review`:

1. **Axis convention inverted in `formation.py`.** Every other module treats x as
   pitch length (`homography._standard_corners`, `pitch_control` grids,
   `pressing`'s goal at `[pitch_length, pitch_width/2]`), but `_mean_depths` read
   `pitch_pos[1]` as depth — and its 18 tests baked in the same inversion, as did
   `CLAUDE.md`. Harmless while `pitch_pos` was unset; a confidently wrong
   formation the moment homography landed.
2. **`track.pitch_history` was never populated anywhere**, which also silently
   zeroed `pitch_control.compute_player_pitch_control_summary` and
   `pressing.compute_recovery_shadow_score`.
3. **Frame-loop aggregation was a no-op.** The tracker puts the _same_ `Track`
   objects in every `TrackedFrame`, so summing `pitch_pos` per frame averaged the
   final frame N times.
4. **Stages 3 and 4 ran before stage 5 published positions**, so pitch control and
   pressing kept using their own linear pixel map even when calibrated — two
   coordinate systems in one report. Both now take `homography=`.
5. **Match API trusted the caller for identity.** Bare `db.get(Match, match_id)`
   everywhere, `list_matches` took `academy_id` from a query param,
   `create_match` from the request body. The existing suite could not have caught
   it: conftest's auth override returned a fixed `_DUMMY_ACADEMY_ID` that never
   matched the academy `seeded` created, so no test ever made an authorised
   request.

Also: positions now come from the bbox bottom edge (ground contact) rather than
its centre; projected positions are clamped to the pitch ±5 m; a ragged
`pitch_corners` JSON row degrades instead of failing the match; and
`home_defends_end` is ignored without a working homography. Fixed a pre-existing
red CI lint job (unused `pytest` import failing `ruff check .` since `a5f88be`).

## Failed Attempts

- Nothing failed outright. Two things not to re-litigate:
  - **`own_goal_end` cannot be derived from the pitch corners.** A homography says
    where the goals _are_, not who defends which one. It must be supplied per match.
  - **A code-review finding claimed the homography turns 5 px of jitter into
    46 m/s vs 7.9 m/s before.** Measured against a realistic quad it is
    **0.64 m → 16.1 m/s** vs 10.6 m/s for the linear fallback — 1.5× amplification,
    not 6×, and no `inf`. The clamp was kept (off-pitch projections are real); the
    proposed speed cap was skipped, since frame-differenced speed already exceeded
    human limits before this change.

## Next steps

1. **`api/routers/players.py` scoping** — identical bug class, still open:
   `/stats`, `/profile`, `/heatmap`, `/prediction` load by player id with no
   academy check, and `create_player` takes `academy_id` from the body. Copy the
   `get_scoped_match` pattern into a `get_scoped_player`; conftest is already
   realigned. Short, mechanical, and closes a half-open hole.
2. **Corner-picker UI** — the highest-value item. Click four corners on a still,
   plus an explicit "which goal does the home team defend?" toggle ("low" = goal
   on the left of frame). Without it nothing shipped this session is reachable.
   Pairs with **re-processing**: upload starts the pipeline immediately, so
   calibration saved afterwards only applies to the next run.
3. **Add opencv to `requirements-ci.txt`** so `tests/test_metrics/`,
   `tests/test_utils/` and `tests/test_pipeline/` run in CI — 100 tests are
   currently local-only.
4. **Half-time end swap** — `home_defends_end` describes the whole video, so a
   full-match upload mirrors one half's formation. Needs a per-half split.
5. Backlog: Re-ID across occlusions (TransReID/OSNet, needs torch); pgvector
   player search; unify the three copies of the linear pixel→metre fallback
   (`run_pipeline.to_pitch`, `pressing.py:90`, `pitch_control.py:174`).

## How to resume / verify

- `cd /Users/amrabujabal/Downloads/football-ai`
- CI scope: `/usr/local/bin/python3.11 -m pytest tests/test_api/ tests/test_db/ -q` → 145 pass
- Wider: `/usr/local/bin/python3.11 -m pytest tests/ -q --ignore=tests/test_detection` → 245 pass
- Lint: `/usr/local/bin/python3.11 -m ruff check .` → clean
- Dashboard: `cd dashboard && ./node_modules/.bin/tsc --noEmit` → clean
- `tests/test_detection/` needs torch/ultralytics — not installed here.
- API live: `https://pitchvision-api-4hxfthgkna-uc.a.run.app/health`
